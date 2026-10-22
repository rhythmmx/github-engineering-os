"""Trusted promotion receipts recover interrupted metadata commits without execution."""

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engineering_os.pipeline import build
from engineering_os.state import Store


FILES = ("health.py", "spec.json", "README.md", "cli.py", "test_health.py", "validation.json")


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.database = self.root / "state.db"
        self.store = Store(self.database)
        self.target = self.root / "output"

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def expire(self):
        self.store.db.execute("UPDATE tasks SET lease_until=0 WHERE id='health-inspector'")
        self.store.db.commit()

    def snapshot(self):
        return {p.name: p.read_bytes() for p in self.target.iterdir() if p.is_file()}

    def interrupt_after_promotion(self):
        original = self.store.finish

        def interrupt(task, status, detail):
            if status == "ready_for_review":
                raise KeyboardInterrupt("simulated interruption after rename")
            return original(task, status, detail)

        with patch.object(self.store, "finish", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                build("health-inspector", self.target, self.store)
        self.assertTrue(self.target.is_dir())
        self.assertEqual(set(p.name for p in self.target.iterdir()), set(FILES))
        self.assertEqual(self.store.report()[0]["status"], "building")

    def assert_recovery_refused_without_execution_or_changes(self):
        before = self.snapshot()
        self.expire()
        with patch("engineering_os.pipeline.subprocess.run") as run:
            with self.assertRaises((ValueError, FileExistsError)):
                build("health-inspector", self.target, self.store)
            run.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_restart_recovers_promoted_output_without_execution_or_rewriting(self):
        self.interrupt_after_promotion()
        before = self.snapshot()
        self.expire()
        self.store.close()
        self.store = Store(self.database)
        with patch("engineering_os.pipeline.subprocess.run") as run:
            report = build("health-inspector", self.target, self.store)
            run.assert_not_called()
        self.assertEqual(report["status"], "ready_for_review")
        self.assertTrue(report["recovered"])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.store.report()[0]["status"], "ready_for_review")
        self.assertEqual(self.store.report()[0]["attempts"], 2)

    def test_metadata_runtime_failure_can_recover_on_retry(self):
        original = self.store.finish
        failed = False

        def fail_once(task, status, detail):
            nonlocal failed
            if status == "ready_for_review" and not failed:
                failed = True
                raise RuntimeError("metadata commit unavailable")
            return original(task, status, detail)

        with patch.object(self.store, "finish", side_effect=fail_once):
            with self.assertRaises(RuntimeError):
                build("health-inspector", self.target, self.store)
        self.assertEqual(self.store.report()[0]["status"], "needs_repair")
        before = self.snapshot()
        with patch("engineering_os.pipeline.subprocess.run") as run:
            report = build("health-inspector", self.target, self.store)
            run.assert_not_called()
        self.assertTrue(report["recovered"])
        self.assertEqual(self.snapshot(), before)

    def test_modified_file_is_not_adopted(self):
        self.interrupt_after_promotion()
        (self.target / "health.py").write_text(
            "raise RuntimeError('do not execute')", encoding="utf-8"
        )
        self.assert_recovery_refused_without_execution_or_changes()

    def test_extra_file_is_not_adopted(self):
        self.interrupt_after_promotion()
        (self.target / "extra.py").write_text("PRIVATE", encoding="utf-8")
        self.assert_recovery_refused_without_execution_or_changes()

    def test_existing_output_without_receipt_is_not_adopted(self):
        self.target.mkdir()
        (self.target / "README.md").write_text("Caller-owned output", encoding="utf-8")
        self.assert_recovery_refused_without_execution_or_changes()

    def test_receipt_for_different_destination_does_not_authorize_adoption(self):
        self.interrupt_after_promotion()
        self.expire()
        self.assertTrue(self.store.claim("health-inspector"))
        receipt = self.store.load_promotion("health-inspector")
        self.store.prepare_promotion("health-inspector", self.root / "other", receipt["inventory"])
        self.assert_recovery_refused_without_execution_or_changes()

    def test_receipt_persists_but_is_not_exposed_in_task_report(self):
        self.store.seed("health-inspector")
        self.assertTrue(self.store.claim("health-inspector"))
        inventory = {name: hashlib.sha256(name.encode()).hexdigest() for name in FILES}
        self.store.prepare_promotion("health-inspector", self.target, inventory)
        self.store.close()
        self.store = Store(self.database)
        self.assertEqual(
            self.store.load_promotion("health-inspector"),
            {"destination": str(self.target.resolve()), "inventory": inventory},
        )
        self.assertEqual(
            set(self.store.report()[0]), {"id", "status", "attempts", "lease_until", "detail"}
        )
        self.assertIsNone(self.store.load_promotion("unknown-task"))

    def test_stale_owner_cannot_replace_receipt(self):
        self.store.seed("health-inspector")
        self.assertTrue(self.store.claim("health-inspector"))
        inventory = {name: "0" * 64 for name in FILES}
        self.store.prepare_promotion("health-inspector", self.target, inventory)
        self.expire()
        replacement = Store(self.database)
        try:
            self.assertTrue(replacement.claim("health-inspector"))
            with self.assertRaises(ValueError):
                self.store.prepare_promotion("health-inspector", self.root / "wrong", inventory)
            self.assertEqual(
                replacement.load_promotion("health-inspector")["destination"],
                str(self.target.resolve()),
            )
        finally:
            replacement.close()

    def test_incomplete_or_malformed_inventory_rejected(self):
        self.store.seed("health-inspector")
        self.assertTrue(self.store.claim("health-inspector"))
        valid = {name: "0" * 64 for name in FILES}
        for inventory in (
            {},
            {"health.py": "0" * 64},
            {**valid, "../escape": "0" * 64},
            {**valid, "health.py": "A" * 64},
            {**valid, "health.py": "not-a-hash"},
        ):
            with self.subTest(inventory=inventory), self.assertRaises(ValueError):
                self.store.prepare_promotion("health-inspector", self.target, inventory)
        self.assertIsNone(self.store.load_promotion("health-inspector"))

    def test_corrupt_persisted_receipt_fails_closed(self):
        self.store.seed("health-inspector")
        self.assertTrue(self.store.claim("health-inspector"))
        self.store.prepare_promotion(
            "health-inspector", self.target, {name: "0" * 64 for name in FILES}
        )
        self.store.db.execute(
            "UPDATE promotions SET inventory=? WHERE task_id=?",
            ('{"health.py":"PRIVATE_BAD_HASH"}', "health-inspector"),
        )
        self.store.db.commit()
        with self.assertRaises(ValueError) as caught:
            self.store.load_promotion("health-inspector")
        self.assertNotIn("PRIVATE_BAD_HASH", str(caught.exception))

    def test_prepare_requires_active_building_lease(self):
        self.store.seed("health-inspector")
        inventory = {name: "0" * 64 for name in FILES}
        with self.assertRaises(ValueError):
            self.store.prepare_promotion("health-inspector", self.target, inventory)
        self.assertTrue(self.store.claim("health-inspector"))
        self.expire()
        with self.assertRaises(ValueError):
            self.store.prepare_promotion("health-inspector", self.target, inventory)
