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
partial output; ordinary write/test failures can retry the same destination. Completed output is
promoted only after checks. A hard process stop can leave a hidden staging directory; inspect and
remove it manually only after confirming no worker owns it. Existing user output is never reused.

Filesystem promotion and SQLite state commit are not one transaction. A crash between them leaves
verified output that needs manual reconciliation before retrying; no crash-complete or distributed
recovery is claimed. This boundary must be solved before unattended arbitrary code generation.
