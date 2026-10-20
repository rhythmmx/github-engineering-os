"""Compare deterministic failure categories in offline response replays."""

from .evaluation import evaluate_suite


def compare_suites(baseline: dict, candidate: dict) -> dict:
    """Compare matching expectations, returning only IDs and failure categories.

    A passing comparison means no new failure category appeared in any case.
    Existing failures can remain, and changes within one category are invisible.
    This does not establish semantic response quality or citation support.
    Both inputs are validated by the evaluator; neither input is modified.
    """
    baseline_report = evaluate_suite(baseline)
    candidate_report = evaluate_suite(candidate)
    baseline_cases = {case["id"]: case for case in baseline["cases"]}
    candidate_cases = {case["id"]: case for case in candidate["cases"]}
    if baseline_cases.keys() != candidate_cases.keys():
        raise ValueError("Comparison requires matching case identifiers")

    for case_id, before in baseline_cases.items():
        after = candidate_cases[case_id]
        for field in ("required_phrases", "forbidden_phrases"):
            if {value.casefold() for value in before[field]} != {
                value.casefold() for value in after[field]
            }:
                raise ValueError("Comparison requires matching expectations")
        for field in ("allowed_citations", "required_citations"):
            if set(before[field]) != set(after[field]):
                raise ValueError("Comparison requires matching expectations")

    baseline_results = {case["id"]: case for case in baseline_report["cases"]}
    candidate_results = {case["id"]: case for case in candidate_report["cases"]}
    results = []
    for case_id in sorted(baseline_cases):
        before_failures = baseline_results[case_id]["failures"]
        after_failures = candidate_results[case_id]["failures"]
        results.append(
            {
                "id": case_id,
                "new_failures": [code for code in after_failures if code not in before_failures],
                "resolved_failures": [
                    code for code in before_failures if code not in after_failures
                ],
                "remaining_failures": [code for code in after_failures if code in before_failures],
            }
        )
    regressed = sum(bool(case["new_failures"]) for case in results)
    return {
        "schema_version": 1,
        "cases_total": len(results),
        "regressed_cases": regressed,
        "resolved_cases": sum(bool(case["resolved_failures"]) for case in results),
        "new_failure_count": sum(len(case["new_failures"]) for case in results),
        "resolved_failure_count": sum(len(case["resolved_failures"]) for case in results),
        "baseline_passed_cases": baseline_report["cases_passed"],
        "candidate_passed_cases": candidate_report["cases_passed"],
        "baseline_passed": baseline_report["passed"],
        "candidate_passed": candidate_report["passed"],
        "passed": regressed == 0,
        "cases": results,
    }
