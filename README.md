# GitHub Engineering OS

A conservative Python work queue, project template pipeline and offline repository health inspector.
For maintainers who want evidence before making repository changes.

## Working capabilities

Priority scoring, SQLite transactional leases, bounded retries, interrupted-task recovery,
tracked-file hygiene checks, a tested health-inspector generator, GitHub activity reads,
offline saved-response regression checks, and CI plus daily maintenance report workflows.
No runtime Python dependencies or live model calls.

```mermaid
flowchart LR
  Backlog --> Ranking --> Specification
  Specification --> Lease[SQLite lease and retry budget]
  Lease --> Template --> Execution[Compile and isolated test process]
  Execution --> Review[Ready for human review]
  Review --> Plan[Private publication plan]
  Repository --> Health --> Report[Actions summary and artifact]
```

## Install and run

Python 3.11+ and Git required; GitHub reads additionally require authenticated `gh`.
From this directory, create a virtual environment with `python -m venv .venv`.
Activate it using `.venv/Scripts/Activate.ps1` on Windows or `source .venv/bin/activate` on Unix.

```sh
python -m pip install .
python -m unittest discover -s tests -v
engineering-os discover config/backlog.json
engineering-os build repository-health-inspector generated/health
engineering-os report
engineering-os health .
engineering-os activity YOUR_GITHUB_LOGIN
engineering-os evaluate examples/evaluation/passing.json
engineering-os compare-evaluations examples/evaluation/passing.json examples/evaluation/passing.json
```

The health command requires a Git repository with tracked files. It inspects the entire repository
index even when passed a subdirectory: findings use repository-root paths, not just that subtree.
Untracked files are excluded; unusual filename bytes are handled without printing file names.
It examines path names only, not file contents, and does not recurse into submodule repositories.
Build produces an executable
standalone CLI, specification, tests and validation evidence. Run `python generated/health/cli.py .`.
Build uses a deterministic reviewed template, not an LLM. Candidate originality scores require
manual research; scores in the seed backlog are estimates.

The `evaluate` command checks synthetic or recorded responses against literal phrase and
explicit citation-ID rules, locally. It exits 0/1/2 for pass/rule failure/invalid input and omits
raw answers from reports. It does not judge semantic correctness or call a model. See
[`docs/OFFLINE-EVALUATION.md`](docs/OFFLINE-EVALUATION.md) for format, limits and interpretation.
`compare-evaluations` detects newly failing rule categories against a matching baseline; unchanged
known failures do not fail that regression gate. See [`docs/EVALUATION-COMPARISON.md`](docs/EVALUATION-COMPARISON.md).

## Scheduling and operations

`maintenance.yml` runs daily at 03:17 UTC (08:47 Asia/Kolkata) and on manual dispatch.
Edit cron in YAML to change the schedule; the TOML timezone is informational.
GitHub schedules can be delayed and are not a continuous worker or SLA.
Each maintenance job is read-only, limited to five minutes, concurrency-controlled,
and writes health and backlog reports to the job summary without artifact uploads. Failed runs use GitHub's configured Actions notifications.
No external notification channel is configured. CI performs the longer generation check separately.

Pause using `gh workflow disable maintenance.yml -R OWNER/REPO`; resume with `gh workflow enable`.
Use `gh workflow run maintenance.yml -R OWNER/REPO` to validate after resuming.
Inspect the Actions summary and `gh run list -R OWNER/REPO`.

## State, failure recovery and publication

Local builds persist task state in `state/tasks.db`; leases expire after 15 minutes and
attempts stop at three. Back up SQLite with its backup API while idle. Never share the DB publicly.
Existing output directories are never overwritten. After interruption between promotion and task
completion, retrying the same task, destination and database can recover matching validated output
without executing or rewriting it. A trusted local receipt must match all six files. Wait for the
old lease to expire; the three-attempt limit still applies. Unowned or changed output requires
manual inspection. See [local recovery boundaries](docs/RECOVERY.md).
The scheduled job is stateless and performs no builds or publication. Distributed durable task
storage and recovery across hosted jobs are not implemented.

`publication_plan` validates readiness and creates an inert private publication plan. It never
creates repositories or pushes code. A maintainer must review the source, validation evidence,
licensing and visibility before manually publishing with GitHub CLI. Existing work goes through PRs.
No model API, cloud resources, paid scheduler, or broad credential secret is provisioned.
`GITHUB_TOKEN` is repository-scoped and cannot discover your other private projects by default.

## Quality and limitations

CI runs Ruff, mypy, unit/integration tests and generated-project execution. There is no measured
coverage or vulnerability scan yet. Health findings are path heuristics, not a security audit.
The reviewer is a separate test process, not an independent AI reviewer. No arbitrary code
generation, automatic repair, automatic publication, autonomous project selection, releases,
cost analytics, dashboard UI, or cross-repository maintenance writes are claimed.
No license is granted yet: owner licensing approval is required before public distribution.
See `docs/AUDIT.md`, `docs/VALIDATION.md` and `docs/OPERATIONS.md` for actual evidence and blockers. See `docs/ZERO-BUDGET.md` for the daily multi-agent desktop continuation and policy boundaries.
