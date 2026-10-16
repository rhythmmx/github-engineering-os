"""Offline, deterministic repository checks. Never reads secret file contents."""

from pathlib import Path
import subprocess


def inspect(path: Path) -> dict:
    path = path.resolve()
    if not path.is_dir():
        raise ValueError("Repository directory does not exist")
    result = subprocess.run(
        ["git", "-C", str(path), "ls-files", "-z"],
        capture_output=True,
        timeout=30,
        check=True,
    )
    files = sorted(result.stdout.decode("utf-8").split("\0"))
    files = [f for f in files if f]
    findings = []

    def flag(code: str, severity: str, message: str) -> None:
        findings.append({"code": code, "severity": severity, "message": message})

    if not any(f.lower() == "readme.md" for f in files):
        flag("missing_readme", "medium", "Add a root README with verified setup commands")
    if not any(f.startswith(".github/workflows/") for f in files):
        flag("missing_ci", "high", "Add CI to execute the existing quality checks")
    if not any("test" in f.lower() or "spec" in f.lower() for f in files):
        flag("no_test_paths", "medium", "No test-named paths found; inspect manually")
    if not any(Path(f).name.lower().startswith("license") for f in files):
        flag("missing_license", "info", "Owner must choose licensing before public reuse")
    if any(Path(f).name in {".env", "id_rsa", "id_ed25519"} for f in files):
        flag("sensitive_filename", "high", "Potential sensitive file tracked; inspect privately")
    return {
        "schema_version": 1,
        "tracked_files": len(files),
        "findings": findings,
        "limitations": [
            "Path heuristics only; no coverage or vulnerability claims",
            "Does not read file contents or follow symlinks",
        ],
    }
