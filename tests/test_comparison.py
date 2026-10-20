"""Regression gates compare failure categories without exposing replay content."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from engineering_os.comparison import compare_suites


def case(**changes):
    value = {
        "id": "sample",
        "response": "STRASSE safe",
        "required_phrases": ["straße", "safe"],
        "forbidden_phrases": ["unsafe"],
        "allowed_citations": ["private-source"],
        "required_citations": ["private-source"],
        "citations": ["private-source"],
    }
    value.update(changes)
    return value


def suite(*cases):
    return {"version": 1, "cases": list(cases or [case()])}


class ComparisonTests(unittest.TestCase):
    def test_unchanged_known_failures_are_not_regressions(self):
        source = suite(case(response="missing"))
        result = compare_suites(source, copy.deepcopy(source))
        self.assertTrue(result["passed"])
        self.assertFalse(result["baseline_passed"])
        self.assertFalse(result["candidate_passed"])
        self.assertEqual(result["new_failure_count"], 0)
        self.assertEqual(
            result["cases"],
            [
                {
                    "id": "sample",
                    "new_failures": [],
                    "resolved_failures": [],
                    "remaining_failures": ["missing_required_phrase"],
                }
            ],
        )

    def test_improvement_counts_resolved_case_and_failure(self):
        result = compare_suites(suite(case(citations=[])), suite())
        self.assertTrue(result["passed"])
        self.assertTrue(result["candidate_passed"])
        self.assertEqual(result["resolved_cases"], 1)
        self.assertEqual(result["resolved_failure_count"], 1)
        self.assertEqual(result["baseline_passed_cases"], 0)
        self.assertEqual(result["candidate_passed_cases"], 1)
        self.assertEqual(result["cases"][0]["resolved_failures"], ["missing_required_citation"])

    def test_new_failure_detected_in_already_failing_case(self):
        result = compare_suites(
            suite(case(citations=[])), suite(case(citations=[], response="STRASSE safe UNSAFE"))
        )
        self.assertFalse(result["passed"])
        self.assertEqual(result["regressed_cases"], 1)
        self.assertEqual(result["new_failure_count"], 1)
        self.assertEqual(result["cases"][0]["new_failures"], ["forbidden_phrase_present"])
        self.assertEqual(result["cases"][0]["remaining_failures"], ["missing_required_citation"])

    def test_same_case_can_resolve_and_introduce_failures(self):
        result = compare_suites(suite(case(citations=[])), suite(case(response="safe UNSAFE")))
        self.assertFalse(result["passed"])
        self.assertEqual((result["regressed_cases"], result["resolved_cases"]), (1, 1))
        self.assertEqual((result["new_failure_count"], result["resolved_failure_count"]), (2, 1))
        self.assertEqual(
            result["cases"][0]["new_failures"],
            ["missing_required_phrase", "forbidden_phrase_present"],
        )
        self.assertEqual(result["cases"][0]["resolved_failures"], ["missing_required_citation"])

    def test_case_and_expectation_order_duplicates_and_phrase_casefold_are_equivalent(self):
        baseline = suite(case(id="z"), case(id="a"))
        candidate = suite(
            case(
                id="a",
                required_phrases=["SAFE", "STRASSE", "safe"],
                forbidden_phrases=["UNSAFE", "unsafe"],
                allowed_citations=["private-source", "private-source"],
            ),
            case(id="z"),
        )
        before = copy.deepcopy((baseline, candidate))
        result = compare_suites(baseline, candidate)
        self.assertTrue(result["passed"])
        self.assertEqual([item["id"] for item in result["cases"]], ["a", "z"])
        self.assertEqual((baseline, candidate), before)
        self.assertEqual(compare_suites(baseline, candidate), result)

    def test_case_and_expectation_drift_rejected_without_echoing_rules(self):
        for candidate in (
            suite(case(id="PRIVATE_WRONG_ID")),
            suite(case(required_phrases=["PRIVATE_CHANGED_RULE"])),
            suite(case(forbidden_phrases=["PRIVATE_FORBIDDEN"])),
            suite(
                case(allowed_citations=["PRIVATE_SOURCE"], required_citations=["PRIVATE_SOURCE"])
            ),
            suite(case(required_citations=[])),
            suite(
                case(allowed_citations=["Private-source"], required_citations=["Private-source"])
            ),
        ):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError) as caught:
                compare_suites(suite(), candidate)
            self.assertNotIn("PRIVATE", str(caught.exception))
            self.assertNotIn("Private-source", str(caught.exception))

    def test_validation_applies_to_both_sides(self):
        invalids = [
            {"version": True, "cases": [case()]},
            suite(case(id="same"), case(id="same")),
            suite(case(response=123)),
            suite(case(required_citations=["unlisted"])),
            suite(
                case(
                    required_phrases=[],
                    forbidden_phrases=[],
                    allowed_citations=[],
                    required_citations=[],
                )
            ),
        ]
        for invalid in invalids:
            for baseline, candidate in ((invalid, suite()), (suite(), invalid)):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    compare_suites(baseline, candidate)

    def test_report_contains_only_ids_categories_and_summary(self):
        baseline = suite()
        candidate = suite(
            case(response="PRIVATE_RESPONSE unsafe", citations=["PRIVATE_UNEXPECTED_CITATION"])
        )
        result = compare_suites(baseline, candidate)
        self.assertEqual(
            set(result),
            {
                "schema_version",
                "cases_total",
                "regressed_cases",
                "resolved_cases",
                "new_failure_count",
                "resolved_failure_count",
                "baseline_passed_cases",
                "candidate_passed_cases",
                "baseline_passed",
                "candidate_passed",
                "passed",
                "cases",
            },
        )
        self.assertEqual(
            set(result["cases"][0]),
            {"id", "new_failures", "resolved_failures", "remaining_failures"},
        )
        encoded = json.dumps(result)
        for private in (
            "PRIVATE_RESPONSE",
            "PRIVATE_UNEXPECTED_CITATION",
            "private-source",
            "straße",
            "STRASSE",
        ):
            self.assertNotIn(private, encoded)

    def test_cli_reports_zero_one_and_two_exit_statuses(self):
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "base.json"
            candidate = Path(directory) / "candidate.json"
            base.write_text(json.dumps(suite()), encoding="utf-8")
            for payload, exit_code in (
                (suite(), 0),
                (suite(case(citations=[])), 1),
                (suite(case(id="PRIVATE_DRIFT")), 2),
                ({"version": True}, 2),
            ):
                candidate.write_text(json.dumps(payload), encoding="utf-8")
                run = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "engineering_os.cli",
                        "compare-evaluations",
                        str(base),
                        str(candidate),
                    ],
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                with self.subTest(exit_code=exit_code):
                    self.assertEqual(run.returncode, exit_code, run.stderr)
                    self.assertNotIn("Traceback", run.stderr)
                    self.assertNotIn("PRIVATE_DRIFT", run.stderr + run.stdout)
                    if exit_code != 2:
                        self.assertEqual(json.loads(run.stdout)["passed"], exit_code == 0)
