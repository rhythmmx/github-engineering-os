# Offline response regression checks

This is the first bounded component of the evaluation-workbench backlog: a deterministic runner
for saved responses. It makes no model or network calls, loads no provider credentials, executes
no response content and adds no dependencies. The example responses are manually written synthetic
fixtures, not measured model outputs or evidence of model quality.

## Acceptance and use

Read a bounded suite, validate its schema, evaluate every case consistently, return CI-friendly
exit codes and omit response/rule/citation contents from the output. Preserve existing commands.

```sh
engineering-os evaluate examples/evaluation/passing.json
engineering-os evaluate examples/evaluation/failing.json
```

Exit codes are 0 for all cases passing, 1 for any rule failure, 2 for malformed/inaccessible input.
The second command deliberately exits 1 and produces all four failure codes. Module invocation
`python -m engineering_os.cli evaluate PATH` has the same exit-code behavior as the installed command.

## Suite version 1

The top level contains exactly integer `version: 1` and a nonempty `cases` list. Each case has exactly
`id`, `response`, `required_phrases`, `forbidden_phrases`, `allowed_citations`, `required_citations`
and `citations`. Every list field contains strings. Required citation IDs must be allowed. A case
with all four expectation lists empty is rejected rather than counted as a meaningful assertion.

| Check | Meaning | Failure code |
|---|---|---|
| Required phrases | Every expected phrase is a substring of the response after Unicode case folding | `missing_required_phrase` |
| Forbidden phrases | No configured forbidden phrase occurs under the same matching rule | `forbidden_phrase_present` |
| Citation allowlist | Every separately supplied citation ID is allowed | `unexpected_citation` |
| Required citations | Every required ID appears in the supplied citation list | `missing_required_citation` |

Citation IDs are case sensitive. They are supplied metadata: the runner does not extract citations
from response prose, fetch sources, or verify that a cited source supports a statement. Phrase
checks are literal substrings, not word boundaries, regexes, entailment, or semantic correctness.
Negation and paraphrases can produce misleading passes/failures. Phrase refusals alone do not
establish prompt-injection resistance. Case pass rate is a regression-rule result only.

## Bounds and privacy

The loader reads at most 2,000,001 bytes and rejects suites above 2,000,000 bytes. Version 1 allows
1–200 cases, 16,000 response characters per case and up to 64 strings of 256 characters in each
list. IDs are unique, at most 64 characters, and use ASCII letters/digits/dot/underscore/hyphen,
starting with a letter or digit. Duplicate JSON keys, malformed/deeply nested JSON, non-finite
numbers, unknown fields and inconsistent citation expectations are rejected.

Reports contain schema version, totals, case pass rate, overall pass/fail and each case ID plus
failure codes. They do not copy response text, configured phrases or citation IDs. Case IDs remain
visible: choose non-sensitive labels and keep private suites out of Git. Generic CLI input errors
do not print private paths, exception text or source snippets. This is not a secret scanner or an
account-wide spending control; the existing zero-budget policy still forbids hosted providers.

## Next steps and limitations

No live inference, semantic judge, latency/cost/token measurements, model comparison, network
adapter or automatic prompt optimization is implemented. A future provider adapter requires a
separate explicit budget and security review; zero-budget operation remains offline. Keep recorded
model outputs with truthful provenance if using this for real evaluations. The supplied fixtures
are synthetic and make no claims about any named model.
