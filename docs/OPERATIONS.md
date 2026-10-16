# Operational boundaries

Private-first installation; owner approval required for public publication and licensing.
Keep private audit reports out of public forks. No secrets are stored in this source tree.
For cross-repository reads, use a GitHub App installed only on selected repositories, with
metadata/contents read access. Do not upload the local CLI OAuth credential into Actions.
API reads reserve 100 requests and retry only 502/503/504, at most three attempts.
403/429 stop immediately; re-dispatch after reset rather than spinning or ignoring limits.

Remote rollout checklist: inspect source and local validation, select visibility, select a license,
verify Actions billing allowance, push to a dedicated repository, run Quality and Maintenance
manually, inspect the job summary, then wait for a genuine schedule event. Only that event establishes
scheduled execution. Account quotas are not verified by local credentials alone.

Expansion milestones: durable GitHub issue task adapter; evidence-bound approval manifests;
sandboxed model implementation provider; independent reviewer; repair diffs and attempt budgets;
dependency scanning; cross-repository App access; deduplicated daily notifications.
Do not enable automatic publication before these controls pass integration tests.
