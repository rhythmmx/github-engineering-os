"""A constrained template pipeline; arbitrary model output is never executed."""

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .state import Store


def rank(candidates: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for item in candidates:
        if item["id"] in seen:
            raise ValueError("Duplicate candidate id")
        seen.add(item["id"])
        for field in ("impact", "depth", "effort", "risk"):
            if type(item[field]) is not int or not 1 <= item[field] <= 5:
                raise ValueError("Scores must be integers from 1 to 5")
        result.append(
            {
                **item,
                "priority": 3 * item["impact"] + 2 * item["depth"] - item["effort"] - item["risk"],
            }
        )
    return sorted(result, key=lambda x: (-x["priority"], x["id"]))


def build(task_id: str, destination: Path, store: Store) -> dict:
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,60}", task_id):
        raise ValueError("Invalid project id")
    store.seed(task_id)
    if not store.claim(task_id):
        return {
            "status": "skipped",
            "reason": "Already completed, leased, or retry budget exhausted",
        }
    try:
        if destination.exists():
            raise FileExistsError("Destination exists; refusing to overwrite")
        destination.mkdir(parents=True)
        source = Path(__file__).with_name("health.py")
        shutil.copyfile(source, destination / "health.py")
        spec = {
            "id": task_id,
            "problem": "Identify repository hygiene gaps offline",
            "users": "Maintainers preparing CI and documentation improvements",
            "acceptance": [
                "Tracked files only",
                "No file content disclosure",
                "Stable JSON findings",
                "Reject non-repositories",
            ],
            "status": "testing",
        }
        (destination / "spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
        (destination / "README.md").write_text(
            "# Repository Health Inspector\n\nOffline tracked-file hygiene checks.\n"
            "Run `python -m unittest -v` and `python cli.py PATH`.\n"
            "Checks README, CI, test paths, license and sensitive filenames.\n"
            "Path heuristics do not measure test coverage or detect all secrets.\n",
            encoding="utf-8",
        )
        (destination / "cli.py").write_text(
            "import json, sys\nfrom pathlib import Path\nfrom health import inspect\n"
            "print(json.dumps(inspect(Path(sys.argv[1])), indent=2))\n",
            encoding="utf-8",
        )
        (destination / "test_health.py").write_text(
            "import tempfile, subprocess, unittest\nfrom pathlib import Path\n"
            "from health import inspect\nclass Smoke(unittest.TestCase):\n"
            " def test_empty_repo(self):\n"
            "  with tempfile.TemporaryDirectory() as d:\n"
            "   subprocess.run(['git','init',d], check=True, capture_output=True)\n"
            "   r=inspect(Path(d))\n"
            "   self.assertEqual(r['tracked_files'],0)\n"
            "   self.assertIn('missing_ci',[f['code'] for f in r['findings']])\n"
            " def test_invalid_repo(self):\n"
            "  with tempfile.TemporaryDirectory() as d:\n"
            "   with self.assertRaises(subprocess.CalledProcessError): inspect(Path(d))\n",
            encoding="utf-8",
        )
        checks = [
            [sys.executable, "-m", "compileall", "-q", "."],
            [sys.executable, "-m", "unittest", "-v"],
        ]
        evidence = []
        for command in checks:
            run = subprocess.run(
                command, cwd=destination, capture_output=True, text=True, timeout=120
            )
            evidence.append({"command": command[1:], "exit_code": run.returncode})
            if run.returncode:
                raise RuntimeError("Generated project failed independent execution checks")
        digest = hashlib.sha256((destination / "health.py").read_bytes()).hexdigest()
        report = {
            "status": "ready_for_review",
            "checks": evidence,
            "source_sha256": digest,
            "review": "Automated execution only; human security and licensing review pending",
        }
        (destination / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        store.finish(task_id, "ready_for_review", digest)
        return report
    except Exception as exc:
        store.finish(task_id, "needs_repair", type(exc).__name__)
        raise


def publication_plan(repository: str, validation: dict, approved: bool = False) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid repository")
    if validation.get("status") != "ready_for_review":
        raise ValueError("Quality gates have not passed")
    return {
        "repository": repository,
        "visibility": "private",
        "approved": approved,
        "action": "manual_review_required",
        "writes_performed": False,
    }
