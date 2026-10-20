import argparse
import json
from pathlib import Path

from .github import GitHub
from .evaluation import evaluate_suite, load_suite
from .comparison import compare_suites
from .health import inspect
from .pipeline import build, publication_plan, rank
from .policy import Policy
from .state import Store


def main():
    parser = argparse.ArgumentParser(description="Conservative engineering automation")
    sub = parser.add_subparsers(dest="command", required=True)
    health = sub.add_parser("health")
    health.add_argument("path", type=Path)
    discover = sub.add_parser("discover")
    discover.add_argument("backlog", type=Path)
    generate = sub.add_parser("build")
    generate.add_argument("id")
    generate.add_argument("destination", type=Path)
    generate.add_argument("--state", type=Path, default=Path("state/tasks.db"))
    activity = sub.add_parser("activity")
    activity.add_argument("owner")
    report = sub.add_parser("report")
    report.add_argument("--state", type=Path, default=Path("state/tasks.db"))
    publication = sub.add_parser("publication-plan")
    publication.add_argument("repository")
    publication.add_argument("validation", type=Path)
    publication.add_argument("--policy", type=Path, required=True)
    evaluation = sub.add_parser("evaluate", help="Check saved responses locally; no model calls")
    evaluation.add_argument("suite", type=Path)
    comparison = sub.add_parser(
        "compare-evaluations", help="Compare saved runs under matching evaluation rules"
    )
    comparison.add_argument("baseline", type=Path)
    comparison.add_argument("candidate", type=Path)
    args = parser.parse_args()
    result: dict | list
    exit_code = 0
    if args.command == "health":
        result = inspect(args.path)
    elif args.command == "discover":
        result = rank(json.loads(args.backlog.read_text(encoding="utf-8")))
    elif args.command == "activity":
        result = GitHub().activity(args.owner)
    elif args.command == "evaluate":
        try:
            result = evaluate_suite(load_suite(args.suite))
        except (ValueError, OSError, RecursionError, UnicodeError):
            print(json.dumps({"error": "Invalid or inaccessible evaluation suite"}))
            return 2
        exit_code = 0 if result["passed"] else 1
    elif args.command == "compare-evaluations":
        try:
            result = compare_suites(load_suite(args.baseline), load_suite(args.candidate))
        except (ValueError, OSError, RecursionError, UnicodeError):
            print(json.dumps({"error": "Invalid, inaccessible, or mismatched evaluation suites"}))
            return 2
        exit_code = 0 if result["passed"] else 1
    elif args.command == "publication-plan":
        result = publication_plan(
            args.repository,
            json.loads(args.validation.read_text(encoding="utf-8")),
            approved=True,
            policy=Policy.load(args.policy),
            visibility="public",
        )
    else:
        store = Store(args.state)
        try:
            result = (
                build(args.id, args.destination, store)
                if args.command == "build"
                else store.report()
            )
        finally:
            store.close()
    print(json.dumps(result, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
