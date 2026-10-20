# Compare recorded evaluations

The offline evaluator answers whether each saved response meets explicit rules. A baseline
comparison answers a different question: did a candidate introduce a new failing check category?
This is useful when known failures remain and a new failure would otherwise be hidden behind an
unchanged case pass rate. No provider, model, network or paid service is involved.

## Acceptance and commands

Compare valid suites with the same case IDs and expectations; allow recorded responses and actual
citation metadata to change. Report new/resolved/remaining failure categories by case, with stable
ordering and no raw responses, configured rules or citation IDs. Preserve existing CLI commands.

```sh
engineering-os compare-evaluations examples/evaluation/passing.json examples/evaluation/passing.json
engineering-os compare-evaluations examples/evaluation/passing.json examples/evaluation/regressing.json
```

The first exits 0 with no new failures. The second intentionally exits 1: the candidate's first
synthetic case introduces all four existing failure categories. The examples are manually written
fixtures, not recorded model measurements. Invalid, inaccessible or mismatched suites exit 2 with
a generic JSON error; no private path or response snippet is included.

## Rules cannot silently drift

Both inputs pass the existing version-1 schema validation and each file's actual 2 MB read limit.
Case-ID sets must match, so adding easy cases or dropping failing ones cannot improve the comparison.
The required/forbidden phrase sets must match after the same Unicode case folding used by the
evaluator. Allowed/required citation-ID sets must match exactly and case sensitively. List order,
duplicate entries, and case order do not change the checks and are ignored for alignment.
Changing an expectation instead of a response is an input error, not an improvement. If rules
legitimately change, establish a separately reviewed baseline rather than silently comparing them.

## Interpret the regression gate correctly

Comparison `passed=true` means **no new failing category**, not that the candidate is healthy.
`baseline_passed` and `candidate_passed` state whether all cases pass their absolute checks;
`baseline_passed_cases` and `candidate_passed_cases` retain the absolute case counts. Use the
existing `evaluate` command as an absolute gate when known failures should also block CI.

For each sorted case ID, `new_failures` contains categories failing only in the candidate,
`resolved_failures` those failing only in the baseline, and `remaining_failures` those failing in
both. Category order follows the evaluator. A case can introduce one category and resolve another;
it contributes to both `regressed_cases` and `resolved_cases`. Overall failure counts count
categories per case, not missing phrases or citation IDs.

Granularity is the evaluator's four categories: missing required phrase, forbidden phrase present,
unexpected citation, missing required citation. If both responses already fail required phrases,
switching which phrase is missing is not a new category and can remain undetected by this gate.
It also does not compare semantic correctness, severity, citation support, latency, tokens or cost.
These limits must remain visible when presenting results as portfolio evidence.

## Privacy and provenance

Case IDs remain visible and should be non-sensitive. Responses and expectations are not copied
to reports. Citation metadata is supplied by the fixture author, not extracted or fetched.
Keep real recorded inputs private where appropriate and document their provenance honestly.
This comparison is a deterministic local check, not a secret scanner, model judge, authenticated
provenance system or prompt-injection-resistance certification.

## Verified synthetic example

Actual installed-command regression-fixture output, excerpted below (exit 1). These are
synthetic cases, not a model benchmark.

```json
{
  "cases_total": 2,
  "regressed_cases": 1,
  "new_failure_count": 4,
  "baseline_passed": true,
  "candidate_passed": false,
  "passed": false
}
```
