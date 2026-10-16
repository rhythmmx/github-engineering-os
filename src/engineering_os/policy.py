"""Explicit boundaries for zero-budget work; callers must check before any side effect.

This module does not configure GitHub billing or enforce account-wide spending.
Hosted model providers are deliberately unsupported, including advertised free tiers.
"""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


class PolicyError(ValueError):
    """The requested action is outside the configured policy."""


@dataclass(frozen=True)
class Policy:
    repositories: frozenset[str] = frozenset()
    publication_enabled: bool = False

    @classmethod
    def load(cls, path: Path) -> "Policy":
        """Read an explicit zero-budget policy, failing closed on invalid settings."""
        try:
            with path.open("rb") as stream:
                data = tomllib.load(stream)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise PolicyError("A readable, valid policy file is required") from exc
        if data.get("monthly_budget_usd") != 0 or type(data.get("monthly_budget_usd")) is not int:
            raise PolicyError("This runner requires an explicit integer zero budget")
        if data.get("hosted_providers_enabled") is not False:
            raise PolicyError("Hosted providers must be explicitly disabled")
        enabled = data.get("publication_enabled", False)
        if type(enabled) is not bool:
            raise PolicyError("publication_enabled must be a boolean")
        repositories = data.get("allowed_repositories", [])
        if not isinstance(repositories, list) or any(
            not isinstance(repo, str) or not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repo)
            for repo in repositories
        ):
            raise PolicyError("allowed_repositories must contain exact owner/repository names")
        return cls(frozenset(repo.casefold() for repo in repositories), enabled)

    def require_repository(self, repository: str) -> None:
        """Reject wildcard, URL, malformed, or unlisted destinations."""
        if not isinstance(repository, str) or not re.fullmatch(
            r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repository
        ):
            raise PolicyError("An exact owner/repository name is required")
        if repository.casefold() not in self.repositories:
            raise PolicyError("Repository is outside the explicit allowlist")

    def require_provider(self, provider: str) -> None:
        """Only disabled generation or an already installed local model is allowed.

        'local' does not authorize downloads, subscriptions, or paid inference.
        """
        if provider not in ("disabled", "local"):
            raise PolicyError("Hosted or unknown AI providers are forbidden at zero budget")

    def require_publication(
        self, repository: str, validation: dict, *, visibility: str = "public"
    ) -> None:
        """Check scope and evidence before a caller performs a publication write.

        Validation must include successful, nonempty execution checks. This checks
        evidence structure; the caller must obtain that evidence from trusted tests.
        """
        self.require_repository(repository)
        if not self.publication_enabled:
            raise PolicyError("Publication is disabled")
        if visibility != "public":
            raise PolicyError("Only public portfolio repositories are authorized")
        checks = validation.get("checks")
        if validation.get("status") != "ready_for_review" or not isinstance(checks, list):
            raise PolicyError("Successful execution evidence is required")
        if not checks or any(
            not isinstance(check, dict)
            or type(check.get("exit_code")) is not int
            or check["exit_code"] != 0
            for check in checks
        ):
            raise PolicyError("All execution checks must pass before publication")
