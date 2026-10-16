import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engineering_os.github import GitHub
from engineering_os.health import inspect
from engineering_os.pipeline import build, publication_plan, rank
from engineering_os.state import Store
from engineering_os.policy import Policy, PolicyError


class SystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "tasks.db")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_leases_and_retry_cap(self):
        self.store.seed("a")
        self.assertTrue(self.store.claim("a"))
        self.assertFalse(self.store.claim("a"))
        self.store.finish("a", "needs_repair", "failure")
        self.assertTrue(self.store.claim("a", lease_seconds=-1))
        self.assertTrue(self.store.claim("a", lease_seconds=-1))
        self.assertFalse(self.store.claim("a"))

    def test_persistence(self):
        self.store.seed("a")
        self.store.close()
        self.store = Store(self.root / "tasks.db")
        self.assertEqual(self.store.report()[0]["status"], "planned")

    def test_stale_worker_cannot_finish_reclaimed_task(self):
        self.store.seed("a")
        self.assertTrue(self.store.claim("a", lease_seconds=-1))
        replacement = Store(self.root / "tasks.db")
        try:
            self.assertTrue(replacement.claim("a"))
            with self.assertRaisesRegex(ValueError, "lease expired"):
                self.store.finish("a", "ready_for_review", "stale result")
            replacement.finish("a", "ready_for_review", "current result")
            self.assertEqual(self.store.report()[0]["detail"], "current result")
        finally:
            replacement.close()

    def test_build_and_idempotency(self):
        report = build("health-inspector", self.root / "project", self.store)
        self.assertEqual(report["status"], "ready_for_review")
        self.assertEqual(
            build("health-inspector", self.root / "project", self.store)["status"], "skipped"
        )

    def test_no_overwrite(self):
        with self.assertRaises(FileExistsError):
            build("health-inspector", self.root, self.store)
        self.assertEqual(self.store.report()[0]["status"], "needs_repair")

    def test_failed_build_can_retry_without_partial_destination(self):
        destination = self.root / "project"
        with patch("engineering_os.pipeline.shutil.copyfile", side_effect=OSError("write failure")):
            with self.assertRaises(OSError):
                build("health-inspector", destination, self.store)
        self.assertFalse(destination.exists())
        self.assertEqual(list(self.root.glob(".health-inspector-build-*")), [])
        result = build("health-inspector", destination, self.store)
        self.assertEqual(result["status"], "ready_for_review")
        self.assertEqual(self.store.report()[0]["attempts"], 2)

    def test_path_traversal(self):
        with self.assertRaises(ValueError):
            build("../escape", self.root / "p", self.store)

    def test_health_tracked_only(self):
        subprocess.run(["git", "init", str(self.root)], check=True, capture_output=True)
        (self.root / "README.md").write_text("hello")
        (self.root / ".env").write_text("fake fixture")
        subprocess.run(["git", "-C", str(self.root), "add", "README.md"], check=True)
        report = inspect(self.root)
        self.assertEqual(report["tracked_files"], 1)
        self.assertNotIn("sensitive_filename", [f["code"] for f in report["findings"]])

    def test_rank_validation(self):
        item = dict(id="a", impact=5, depth=4, effort=2, risk=1)
        self.assertEqual(rank([item])[0]["priority"], 20)
        with self.assertRaises(ValueError):
            rank([item, item])

    def test_publication_fails_closed(self):
        with self.assertRaises(ValueError):
            publication_plan("owner/repo", {"status": "needs_repair"})
        self.assertFalse(
            publication_plan("owner/repo", {"status": "ready_for_review"})["writes_performed"]
        )

    def test_approved_plan_requires_explicit_policy_and_successful_evidence(self):
        validation = {"status": "ready_for_review", "checks": [{"exit_code": 0}]}
        with self.assertRaises(PolicyError):
            publication_plan("owner/repo", validation, approved=True)
        policy = Policy(frozenset({"owner/repo"}), True)
        plan = publication_plan(
            "owner/repo", validation, approved=True, policy=policy, visibility="public"
        )
        self.assertTrue(plan["approved"])
        self.assertFalse(plan["writes_performed"])
        with self.assertRaises(PolicyError):
            publication_plan(
                "unrelated/repo", validation, approved=True, policy=policy, visibility="public"
            )

    def test_transient_retry(self):
        bad = subprocess.CompletedProcess([], 1, "", "HTTP 503")
        good = subprocess.CompletedProcess([], 0, json.dumps({"ok": True}), "")
        with (
            patch("engineering_os.github.subprocess.run", side_effect=[bad, good]),
            patch("time.sleep") as sleep,
        ):
            self.assertTrue(GitHub(sleep=sleep).read("user")["ok"])
            sleep.assert_called_once_with(1)

    def test_auth_failure_no_retry(self):
        bad = subprocess.CompletedProcess([], 1, "", "HTTP 401 private details")
        with patch("engineering_os.github.subprocess.run", return_value=bad) as run:
            with self.assertRaisesRegex(RuntimeError, "GitHub read failed"):
                GitHub().read("user")
            self.assertEqual(run.call_count, 1)
