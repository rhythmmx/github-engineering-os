# Recovering an interrupted local template build

A process can stop after validated staging output is renamed into place but before SQLite records
completion. The builder now saves a promotion receipt in SQLite before that rename. It records the
canonical destination and SHA-256 hashes of exactly `health.py`, `spec.json`, `README.md`, `cli.py`,
`test_health.py` and `validation.json`. The receipt is local state and is omitted from task reports.

Retry the original task with the same destination and database after its 15-minute lease expires:

```sh
engineering-os build repository-health-inspector generated/health --state state/tasks.db
```

Recovery requires a new lease within the existing three-attempt budget. It verifies the destination,
exact file inventory and hashes, task ID in the specification, source hash and passing validation
checks. Each file is limited to 2 MB. Linked destinations/files, unexpected entries, changed bytes,
missing receipts and corrupt receipts are rejected. Successful recovery completes task metadata and
returns `recovered: true`; it never executes or rewrites the existing artifact files. New builds
avoid bytecode caches so the promoted directory contains exactly the six recorded files.

The saved receipt describes the original validated template snapshot, not necessarily the current
package revision. Recovered output remains ready for review, not published. Already-completed tasks
are skipped as before; skipping does not revalidate or repair their output.

## Limits and manual reconciliation

Trust the local database, filesystem and cooperating workers. Hashes bind output to that trusted
receipt; they are not an independent attestation. Filesystem rename and SQLite completion are not
one transaction. A worker can lose its lease between recording a receipt and renaming output;
there is no atomic filesystem fencing. Concurrent hostile replacement of files during verification
is outside this recovery model. No file/directory fsync is performed, so sudden power loss is not
guaranteed to preserve bytes. This is local process-interruption recovery, not distributed recovery.

Older output without receipts, mismatches and exhausted attempts require manual diagnosis. Preserve
the output and state for inspection; do not delete output or reset attempts blindly. Use a fresh
destination only after deciding how to reconcile the old task. A hard stop can leave a hidden staging
directory; clean it up only after establishing that no worker owns it. Back up local state using
SQLite's backup API while idle; copying a live database without its WAL is not a safe backup.
Never publish the database: receipts contain local destination paths.
