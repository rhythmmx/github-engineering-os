"""Replay evaluation behavior and hostile-input boundaries without model calls."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from engineering_os.evaluation import evaluate_suite, load_suite


def case(**changes):
    item = {
        "id": "answer-one",
        "response": "The STRASSE guide gives safe instructions.",
        "required_phrases": ["straße", "safe"],
        "forbidden_phrases": ["unsafe"],
        "allowed_citations": ["guide-v1"],
        "required_citations": ["guide-v1"],
        "citations": ["guide-v1"],
    }
    item.update(changes)
    return item


def suite(*cases):
    return {"version": 1, "cases": list(cases or [case()])}


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "suite.json"

    def write(self, value):
        self.path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return self.path

    def test_all_checks_pass_with_unicode_casefold_substrings(self):
        result = evaluate_suite(suite())
        self.assertEqual(result["cases_passed"], 1)
        self.assertEqual(result["cases_total"], 1)
        self.assertEqual(result["pass_rate"], 1.0)
        self.assertEqual(result["cases"], [{"id": "answer-one", "passed": True, "failures": []}])

    def test_each_rule_fails_independently(self):
        for changes, code in (
            ({"response": "safe instructions"}, "missing_required_phrase"),
            ({"response": "STRASSE safe but UNSAFE"}, "forbidden_phrase_present"),
            ({"citations": ["guide-v1", "Guide-v1"]}, "unexpected_citation"),
            ({"citations": []}, "missing_required_citation"),
        ):
            with self.subTest(code=code):
                result = evaluate_suite(suite(case(**changes)))
                self.assertEqual(result["cases_passed"], 0)
                self.assertEqual(result["pass_rate"], 0.0)
                self.assertEqual(result["cases"][0]["failures"], [code])
                self.assertFalse(result["cases"][0]["passed"])

    def test_failures_are_unique_ordered_and_reports_do_not_echo_content(self):
        item = case(
            response="SECRET_ANSWER forbidden SECRET_VALUE",
            required_phrases=["MISSING_PRIVATE_ONE", "MISSING_PRIVATE_TWO"],
            forbidden_phrases=["forbidden", "secret_value"],
            citations=["PRIVATE_CITATION"],
        )
        result = evaluate_suite(suite(item))
        self.assertEqual(
            result["cases"][0],
            {
                "id": "answer-one",
                "passed": False,
                "failures": [
                    "missing_required_phrase",
                    "forbidden_phrase_present",
                    "unexpected_citation",
                    "missing_required_citation",
                ],
            },
        )
        encoded = json.dumps(result)
        for private in (
            item["response"],
            *item["required_phrases"],
            *item["citations"],
            "guide-v1",
        ):
            self.assertNotIn(private, encoded)

    def test_mixed_results_have_correct_denominator_and_do_not_mutate_suite(self):
        source = suite(case(), case(id="answer-two", citations=[]))
        original = copy.deepcopy(source)
        result = evaluate_suite(source)
        self.assertEqual(
            (result["cases_total"], result["cases_passed"], result["pass_rate"]), (2, 1, 0.5)
        )
        self.assertEqual(source, original)

    def test_invalid_structure_is_rejected(self):
        invalid = [
            {"version": True, "cases": [case()]},
            {"version": 2, "cases": [case()]},
            {"version": 1, "cases": []},
            {**suite(), "unknown": "PRIVATE_VALUE"},
            suite(case(id="same"), case(id="same")),
            suite(case(id="not an ascii id!")),
            suite(case(response=123)),
            suite(case(required_phrases="safe")),
            suite(case(required_phrases=[""])),
            suite(case(required_citations=["not-allowed"])),
            suite(
                case(
                    required_phrases=[],
                    forbidden_phrases=[],
                    allowed_citations=[],
                    required_citations=[],
                )
            ),
            suite({key: value for key, value in case().items() if key != "response"}),
            suite(case(extra=True)),
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                evaluate_suite(value)

    def test_limits_reject_oversized_responses_cases_and_files(self):
        for value in (
            suite(case(response="x" * 16001)),
            suite(*[case(id=f"case-{i}") for i in range(201)]),
        ):
            with self.subTest(value_type=type(value)), self.assertRaises(ValueError):
                evaluate_suite(value)
        self.path.write_bytes(b" " * 2_000_001)
        with self.assertRaises(ValueError):
            load_suite(self.path)

    def test_loader_rejects_duplicate_keys_nonfinite_and_malformed_json(self):
        for text in (
            '{"version":1,"version":1,"cases":[]}',
            json.dumps(suite()).replace('"response":', '"response":"duplicate","response":'),
            '{"version":NaN,"cases":[]}',
            '{"version":Infinity,"cases":[]}',
            '{"version":1,"cases":[',
        ):
            self.path.write_text(text, encoding="utf-8")
            with self.subTest(text=text), self.assertRaises(ValueError):
                load_suite(self.path)

    def test_utf8_file_loads_and_non_utf8_is_rejected(self):
        self.assertEqual(load_suite(self.write(suite())), suite())
        self.path.write_bytes(b"\xff")
        with self.assertRaises(ValueError):
            load_suite(self.path)

    def test_cli_exit_codes_and_json_report(self):
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        for value, expected in (
            (suite(), 0),
            (suite(case(citations=[])), 1),
            ({"PRIVATE_INVALID": True}, 2),
        ):
            run = subprocess.run(
                [sys.executable, "-m", "engineering_os.cli", "evaluate", str(self.write(value))],
                env=environment,
                capture_output=True,
                text=True,
                timeout=15,
            )
            with self.subTest(expected=expected):
                self.assertEqual(run.returncode, expected, run.stderr)
                self.assertNotIn("Traceback", run.stderr)
                self.assertNotIn("PRIVATE_INVALID", run.stdout + run.stderr)
                if expected != 2:
                    self.assertEqual(json.loads(run.stdout)["cases_total"], 1)

    def test_list_entry_and_identifier_limits_are_enforced(self):
        for changes in (
            {"required_phrases": ["safe"] * 65},
            {"forbidden_phrases": ["x" * 257]},
            {"allowed_citations": ["x" * 257]},
            {"citations": [False]},
            {"id": "a" * 65},
            {"id": "café"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                evaluate_suite(suite(case(**changes)))
        boundary = case(
            id="a" * 64,
            response="s" * 16000,
            required_phrases=["s" * 256] * 64,
            forbidden_phrases=[],
        )
        self.assertTrue(evaluate_suite(suite(boundary))["passed"])

    def test_invalid_errors_do_not_echo_private_inputs(self):
        self.path.write_text('{"PRIVATE_SECRET": "raw answer", broken}', encoding="utf-8")
        with self.assertRaises(ValueError) as caught:
            load_suite(self.path)
        self.assertNotIn("PRIVATE_SECRET", str(caught.exception))
        self.assertNotIn("raw answer", str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            evaluate_suite(suite(case(id="PRIVATE SECRET INVALID")))
        self.assertNotIn("PRIVATE SECRET INVALID", str(caught.exception))
