"""A constrained template pipeline; arbitrary model output is never executed."""

import hashlib
import json
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from pathlib import Path

from .state import PROMOTION_FILES, Store
from .policy import Policy, PolicyError

MAX_ARTIFACT_BYTES = 2_000_000


def _is_link(path: Path) -> bool:
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def _artifact_bytes(target: Path) -> dict[str, bytes]:
    """Read only the exact small, regular, nonlinked template artifacts."""
    try:
        if _is_link(target) or not target.is_dir():
            raise ValueError
        if {entry.name for entry in target.iterdir()} != PROMOTION_FILES:
            raise ValueError
        content = {}
        for name in sorted(PROMOTION_FILES):
            artifact = target / name
            if _is_link(artifact) or not artifact.is_file():
                raise ValueError
            with artifact.open("rb") as stream:
                data = stream.read(MAX_ARTIFACT_BYTES + 1)
            if len(data) > MAX_ARTIFACT_BYTES:
                raise ValueError
            content[name] = data
        return content
    except (OSError, ValueError):
        raise FileExistsError("Output is not an exact recoverable template artifact set") from None


def _recover_promotion(task_id: str, target: Path, store: Store) -> dict:
    receipt = store.load_promotion(task_id)
    if receipt is None or _is_link(target) or Path(receipt["destination"]) != target.resolve():
        raise FileExistsError("Existing output does not match a recorded promotion")
    content = _artifact_bytes(target)
    inventory = {name: hashlib.sha256(data).hexdigest() for name, data in content.items()}
    if inventory != receipt["inventory"]:
        raise FileExistsError("Existing output differs from its recorded promotion")
    try:
        report = json.loads(content["validation.json"].decode("utf-8"))
        spec = json.loads(content["spec.json"].decode("utf-8"))
        checks = report.get("checks") if isinstance(report, dict) else None
        if (
            not isinstance(spec, dict)
            or spec.get("id") != task_id
            or not isinstance(report, dict)
            or report.get("status") != "ready_for_review"
            or report.get("source_sha256") != inventory["health.py"]
            or not isinstance(checks, list)
            or not checks
            or any(
                not isinstance(check, dict)
                or type(check.get("exit_code")) is not int
                or check["exit_code"] != 0
                for check in checks
            )
        ):
            raise ValueError
    except (ValueError, UnicodeError, RecursionError):
        raise FileExistsError("Recorded output has invalid validation evidence") from None
    store.finish(task_id, "ready_for_review", report["source_sha256"])
    return {**report, "recovered": True}


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
        if _is_link(destination):
            raise FileExistsError("Linked destinations cannot be recovered or overwritten")
        if destination.exists():
            return _recover_promotion(task_id, destination, store)
        target = destination.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        # Staging is owned by this invocation; never delete or reuse caller output.
        with TemporaryDirectory(prefix=f".{task_id}-build-", dir=target.parent) as stage_dir:
            destination = Path(stage_dir) / "project"
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
                [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; "
                    "[compile(p.read_bytes(), str(p), 'exec') for p in Path('.').glob('*.py')]",
                ],
                [sys.executable, "-B", "-m", "unittest", "-v"],
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
            (destination / "validation.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
            files = _artifact_bytes(destination)
            inventory = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
            store.prepare_promotion(task_id, target, inventory)
            if target.exists() or _is_link(target):
                raise FileExistsError("Destination appeared during build; refusing to overwrite")
            destination.rename(target)
        store.finish(task_id, "ready_for_review", digest)
        return report
    except Exception as exc:
        try:
            store.finish(task_id, "needs_repair", type(exc).__name__)
        except ValueError:
            # An expired worker must not update a replacement worker's task.
            pass
        raise


def publication_plan(
    repository: str,
    validation: dict,
    approved: bool = False,
    *,
    policy: Policy | None = None,
    visibility: str = "private",
) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid repository")
    if validation.get("status") != "ready_for_review":
        raise ValueError("Quality gates have not passed")
    if approved:
        if policy is None:
            raise PolicyError("An explicit policy is required for an approved publication plan")
        policy.require_publication(repository, validation, visibility=visibility)
    return {
        "repository": repository,
        "visibility": visibility,
        "approved": approved,
        "action": "manual_review_required",
        "writes_performed": False,
    }
