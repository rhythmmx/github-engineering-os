import tempfile
import unittest
from pathlib import Path

from engineering_os.policy import Policy, PolicyError


class PolicyTests(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.toml"
            path.write_text(text, encoding="utf-8")
            return Policy.load(path)

    def test_missing_file_fails_closed(self):
        with self.assertRaises(PolicyError):
            Policy.load(Path("missing-policy-file.toml"))

    def test_unsafe_or_malformed_configuration_rejected(self):
        for text in (
            "broken = [",
            "monthly_budget_usd = 1\nhosted_providers_enabled = false",
            "monthly_budget_usd = false\nhosted_providers_enabled = false",
            "monthly_budget_usd = 0",
            "monthly_budget_usd = 0\nhosted_providers_enabled = false\n"
            'allowed_repositories = ["owner/*"]',
            "monthly_budget_usd = 0\nhosted_providers_enabled = false\n"
            'publication_enabled = "true"',
        ):
            with self.subTest(text=text), self.assertRaises(PolicyError):
                self.load(text)

    def test_defaults_deny_publication_and_repositories(self):
        policy = self.load("monthly_budget_usd = 0\nhosted_providers_enabled = false")
        self.assertFalse(policy.publication_enabled)
        with self.assertRaises(PolicyError):
            policy.require_repository("owner/project")
        with self.assertRaises(PolicyError):
            Policy(frozenset({"owner/project"})).require_publication("owner/project", {})

    def test_exact_repository_allowlist(self):
        policy = Policy(frozenset({"owner/project"}))
        policy.require_repository("Owner/Project")
        for repository in (
            "other/project",
            "owner/project-extra",
            "https://github.com/owner/project",
        ):
            with self.subTest(repository=repository), self.assertRaises(PolicyError):
                policy.require_repository(repository)

    def test_hosted_providers_denied_even_when_advertised_free(self):
        policy = Policy()
        for provider in ("openai", "anthropic", "free-tier", "", "LOCAL"):
            with self.subTest(provider=provider), self.assertRaises(PolicyError):
                policy.require_provider(provider)
        policy.require_provider("local")
        policy.require_provider("disabled")

    def test_publication_requires_public_destination_and_execution_evidence(self):
        policy = Policy(frozenset({"owner/project"}), True)
        valid = {"status": "ready_for_review", "checks": [{"exit_code": 0}]}
        policy.require_publication("owner/project", valid)
        with self.assertRaises(PolicyError):
            policy.require_publication("owner/project", valid, visibility="private")
        for evidence in (
            {},
            {"status": "needs_repair", "checks": [{"exit_code": 0}]},
            {"status": "ready_for_review", "checks": []},
            {"status": "ready_for_review", "checks": [{"exit_code": 1}]},
            {"status": "ready_for_review", "checks": [{"exit_code": False}]},
            {"status": "ready_for_review", "checks": [None]},
        ):
            with self.subTest(evidence=evidence), self.assertRaises(PolicyError):
                policy.require_publication("owner/project", evidence)

    def test_checked_in_policy_limits_scope(self):
        policy = Policy.load(Path(__file__).resolve().parents[1] / "config" / "policy.toml")
        policy.require_repository("rhythmmx/github-engineering-os")
        policy.require_repository("rhythmmx/contract-sentinel")
        with self.assertRaises(PolicyError):
            policy.require_repository("rhythmmx/private-project")
