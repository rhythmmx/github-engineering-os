# Zero-additional-budget operation

The user authorizes daily useful public portfolio work with multiple agents, using existing
included Codex usage. No API keys, credits, paid services, hosting or larger runners are provisioned.
Exhausted included usage is a blocker, never a reason to buy credits or change subscriptions.

## Two different schedulers

- GitHub Actions: daily at 08:47 Asia/Kolkata. Runs a stateless health/backlog report, with read-only
  repository permissions, a five-minute timeout, and no new artifact uploads. It does not generate
  arbitrary code or run this Codex conversation. Read its job summary for both reports.
- Desktop scheduled continuation: this chat resumes daily at 09:00 Asia/Kolkata. The parent uses
  up to three subagents for implementation, testing and independent review when usage permits.
  Local repositories require the computer on and the app running. No first unattended execution
  has been verified yet. Manage or pause it in the app's Scheduled view.

Official scheduling requirements:
https://learn.chatgpt.com/docs/automations?surface=app

The daily goal is one useful checked milestone or review-ready PR, not guaranteed commits.
No changes are published merely to fill a contribution graph. Existing projects use branches and
PRs; hosted CI and independent review precede merging. No unrelated private projects are modified.

## Policy and publication preflight

`config/policy.toml` requires integer zero budget, hosted providers disabled, an exact repository
allowlist and explicit publication enablement. `Policy` rejects hosted providers, including
advertised free tiers. Approved publication plans call that guard and require nonempty passing
execution evidence. Missing policy or an unrelated destination fails closed.

```sh
engineering-os publication-plan rhythmmx/github-engineering-os VALIDATION.json --policy config/policy.toml
```

The validation JSON must come from actual checks and include `status: ready_for_review` and a
nonempty `checks` array with integer zero `exit_code` values. The preflight produces an inert plan;
it never pushes or creates a PR. The desktop agent performs authorized GitHub operations separately.
Policy labels/evidence are trusted inputs, not a sandbox, cryptographic attestation, account-wide
billing control, or a verification that a local model is installed. No provider execution exists
in this package; `local` would require separate installation and cost verification before use.

Standard public GitHub runner minutes are free; account storage and other services have separate
limits. No new report artifacts or runner caches are created by this workflow. Existing historical
artifacts follow their original retention settings.
https://docs.github.com/en/billing/concepts/product-billing/github-actions

## Build recovery boundary

Generation and checks run in an invocation-owned staging directory. Failed checks never publish
partial output; ordinary write/test failures can retry the same destination. Before promotion,
the active lease owner records the destination and exact six-file hash inventory in local SQLite.
A retry can adopt matching validated output without executing or changing existing files.
Unowned, changed or incomplete output fails closed. See [RECOVERY.md](RECOVERY.md).

Filesystem promotion and SQLite completion remain separate transactions. Recovery handles process
interruption using trusted local state and cooperative workers; it does not atomically fence
filesystem writes after lease expiry or concurrent local tampering. File/directory fsync is not
performed, so power-loss durability is not guaranteed. A hard stop can leave hidden staging files;
inspect them manually after confirming no worker owns them. Attempts remain capped at three.
No distributed recovery, arbitrary generation or automatic publication is enabled.
