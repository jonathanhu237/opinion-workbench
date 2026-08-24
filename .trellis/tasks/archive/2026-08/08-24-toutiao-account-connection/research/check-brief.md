# Independent check brief

Review the full uncommitted parent and MediaCrawler submodule diff for the approved Toutiao account
connection task. Include untracked files explicitly; `git diff` alone will not show them.

## Required audit points

- Confirm the scoped positive DOM selector cannot be satisfied by content-author/profile links or
  login-entry drift. Unknown/currently unproven DOM must remain non-connected.
- Confirm borrowed-browser auth retains an official challenge page without navigation, refresh,
  clicks, Cookie injection, QR extraction, input, or challenge interaction.
- Confirm `connected` comes only from a fresh trusted-origin three-state check before/after manual
  work, with malformed/contradictory/browser-failure states failing closed.
- Confirm auth validates the CLI safety boundary before browser startup and cannot reach proxy,
  `BrowserAuthStateStore`, search/detail/creator/comment/media/store/database work.
- Confirm CDP failure has no standard-browser fallback; cancellation and every terminal path close
  only registered task pages and cannot close the borrowed context/browser/process or pre-existing
  tabs.
- Regress normal Toutiao search: fresh standard visible context, CDP ignored, optional state-store
  order, separate Auth/Search Pages, one search navigation, and storage behavior stay unchanged.
- Confirm `wb | dy | ks | toutiao` typed protocol/worker mapping and all 12 ordered foreign-event
  failures, while the public Toutiao catalog still returns 409 and React remains untouched.
- Check task PRD/design/implementation/evidence consistency, especially the auth-only no-click
  behavior and held rollout gate.
- Check secret/privacy logging boundaries and reject tests that would pass if the intended safety
  behavior were removed.

Self-fix only verified mechanical/local issues. Report any judgment issue with concrete file/line
evidence. Do not run a real browser/login, enable the catalog, commit, push, or modify unrelated
runtime data. You are not alone in this repository; preserve all active task and implementation
changes and do not revert them.
