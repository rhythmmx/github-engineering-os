"""Real Git index fixtures preserve whole-repository scope and private filenames."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from engineering_os.health import inspect


class HealthScopeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "repository space café"
        self.root.mkdir()
        self.git("init")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)

    def track(self, name, content="fixture"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.git("add", "--force", "--", name)
        return path

    def test_root_nested_and_sibling_paths_inspect_identical_whole_index(self):
        self.track("README.md")
        self.track(".github/workflows/check.yml")
        self.track("tests/test_fixture.py")
        self.track("LICENSE")
        self.track("packages/sibling/module.py")
        nested = self.root / "packages" / "deep" / "empty"
        nested.mkdir(parents=True)
        expected = inspect(self.root)
        self.assertEqual(expected["tracked_files"], 5)
        self.assertEqual(expected["findings"], [])
        self.assertEqual(inspect(nested), expected)
        self.assertEqual(inspect(self.root / "packages" / "sibling"), expected)

    def test_untracked_hygiene_files_and_secrets_are_ignored(self):
        nested = self.root / "nested"
        nested.mkdir()
        for name in ("README.md", ".env", "LICENSE"):
            (self.root / name).write_text("PRIVATE_UNTRACKED", encoding="utf-8")
        (self.root / ".github" / "workflows").mkdir(parents=True)
        (self.root / ".github" / "workflows" / "ci.yml").write_text("fixture", encoding="utf-8")
        (self.root / "test_untracked.py").write_text("fixture", encoding="utf-8")
        self.track("nested/module.py")
        report = inspect(nested)
        self.assertEqual(report["tracked_files"], 1)
        self.assertEqual(
            {f["code"] for f in report["findings"]},
            {"missing_readme", "missing_ci", "no_test_paths", "missing_license"},
        )
        self.assertEqual(report, inspect(self.root))

    def test_tracked_secret_warning_never_discloses_filename_or_content(self):
        self.track("PRIVATE_OWNER/.env", "PRIVATE_SECRET_VALUE")
        nested = self.root / "unrelated"
        nested.mkdir()
        report = inspect(nested)
        self.assertIn("sensitive_filename", {f["code"] for f in report["findings"]})
        encoded = json.dumps(report)
        for private in ("PRIVATE_OWNER", ".env", "PRIVATE_SECRET_VALUE", str(self.root)):
            self.assertNotIn(private, encoded)
        self.assertEqual(report["tracked_files"], 1)

    def test_spaces_and_unicode_filenames_remain_single_tracked_entries(self):
        self.track("source space/東京 café.py")
        self.track("another name.py")
        self.assertEqual(inspect(self.root)["tracked_files"], 2)

    @unittest.skipIf(os.name == "nt", "Windows filenames cannot contain newline")
    def test_newline_filenames_and_repository_root_are_preserved(self):
        renamed = self.root.with_name("repository\nname")
        self.root.rename(renamed)
        self.root = renamed
        self.track("line\nbreak.py")
        self.track("normal.py")
        self.assertEqual(inspect(self.root)["tracked_files"], 2)

    @unittest.skipIf(os.name == "nt", "Raw undecodable filenames require POSIX")
    def test_raw_undecodable_filename_does_not_break_inspection(self):
        raw = os.fsencode(self.root) + b"/private-\xff.py"
        fd = os.open(raw, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        self.git("add", "--", os.fsdecode(b"private-\xff.py"))
        report = inspect(self.root)
        self.assertEqual(report["tracked_files"], 1)
        self.assertNotIn("private-", json.dumps(report))

    def test_non_repository_and_missing_directory_errors_remain_distinct(self):
        outside = Path(self.directory.name) / "not-a-repository"
        outside.mkdir()
        with self.assertRaises(subprocess.CalledProcessError):
            inspect(outside)
        with self.assertRaises(ValueError):
            inspect(outside / "missing")
        regular = outside / "file"
        regular.write_text("fixture", encoding="utf-8")
        with self.assertRaises(ValueError):
            inspect(regular)
