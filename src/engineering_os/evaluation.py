"""Deterministic offline checks of recorded responses, not semantic evaluation."""

import json
import math
from pathlib import Path
import re

MAX_SUITE_BYTES = 2_000_000
LIST_FIELDS = (
    "required_phrases",
    "forbidden_phrases",
    "allowed_citations",
    "required_citations",
    "citations",
)
CASE_FIELDS = {"id", "response", *LIST_FIELDS}
CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", re.ASCII)


def _validate_suite(suite: dict) -> dict:
    if not isinstance(suite, dict) or set(suite) != {"version", "cases"}:
        raise ValueError("Suite requires exactly version and cases")
    if type(suite["version"]) is not int or suite["version"] != 1:
        raise ValueError("Unsupported suite version")
    cases = suite["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 200:
        raise ValueError("Suite requires between 1 and 200 cases")
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != CASE_FIELDS:
            raise ValueError("Case requires exactly the documented fields")
        case_id = case["id"]
        if not isinstance(case_id, str) or CASE_ID.fullmatch(case_id) is None:
            raise ValueError("Invalid case identifier")
        if case_id in seen:
            raise ValueError("Duplicate case identifier")
        seen.add(case_id)
        if not isinstance(case["response"], str) or len(case["response"]) > 16_000:
            raise ValueError("Response must be a string of at most 16000 characters")
        for field in LIST_FIELDS:
            values = case[field]
            if not isinstance(values, list) or len(values) > 64:
                raise ValueError("Case lists must contain at most 64 strings")
            if any(not isinstance(value, str) or not 1 <= len(value) <= 256 for value in values):
                raise ValueError("Case list entries must contain between 1 and 256 characters")
        if not set(case["required_citations"]) <= set(case["allowed_citations"]):
            raise ValueError("Required citations must be allowed")
        if not any(case[field] for field in LIST_FIELDS[:-1]):
            raise ValueError("Case must declare at least one expectation")
    return suite


def load_suite(path: Path) -> dict:
    """Read at most the suite byte limit plus one, rejecting ambiguous JSON."""
    with path.open("rb") as stream:
        content = stream.read(MAX_SUITE_BYTES + 1)
    if len(content) > MAX_SUITE_BYTES:
        raise ValueError("Suite exceeds 2 MB")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("Non-finite JSON numbers are not supported")

    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("Non-finite JSON numbers are not supported")
        return parsed

    try:
        suite = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=reject_constant,
            parse_float=finite_float,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ValueError("Invalid suite JSON") from None
    return _validate_suite(suite)


def evaluate_suite(suite: dict) -> dict:
    """Check phrases and citation IDs in recorded responses without network calls.

    These checks do not establish semantic correctness, citation support, live
    model latency, or token usage. Only case identifiers and failure codes leave
    the evaluator; recorded responses and expectation values remain private.
    """
    _validate_suite(suite)
    results = []
    for case in suite["cases"]:
        response = case["response"].casefold()
        citations = set(case["citations"])
        failures = []
        if any(phrase.casefold() not in response for phrase in case["required_phrases"]):
            failures.append("missing_required_phrase")
        if any(phrase.casefold() in response for phrase in case["forbidden_phrases"]):
            failures.append("forbidden_phrase_present")
        if not citations <= set(case["allowed_citations"]):
            failures.append("unexpected_citation")
        if not set(case["required_citations"]) <= citations:
            failures.append("missing_required_citation")
        results.append({"id": case["id"], "passed": not failures, "failures": failures})
    passed = sum(result["passed"] for result in results)
    return {
        "schema_version": 1,
        "cases_total": len(results),
        "cases_passed": passed,
        "pass_rate": passed / len(results),
        "passed": passed == len(results),
        "cases": results,
    }
