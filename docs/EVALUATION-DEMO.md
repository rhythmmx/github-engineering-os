# Offline fixture demonstration

Actual installed-command output for ngineering-os evaluate examples/evaluation/passing.json.
These are two manually written synthetic cases; this is not a model benchmark.

```json
{
  "schema_version": 1,
  "cases_total": 2,
  "cases_passed": 2,
  "pass_rate": 1.0,
  "passed": true,
  "cases": [
    {
      "id": "build-summary",
      "passed": true,
      "failures": []
    },
    {
      "id": "credential-refusal",
      "passed": true,
      "failures": []
    }
  ]
}
```

The deliberately failing fixture exits 1 with all four failure codes; malformed input exits 2.
No model calls were made. See OFFLINE-EVALUATION.md for limits and interpretation.
