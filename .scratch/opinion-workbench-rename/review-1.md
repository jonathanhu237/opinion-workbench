# Review 1 — cumulative implementation

Fixed baseline: bf4b6ba964d8fabdcc1a711e6abca46a11d192ef
Fixed spec: /tmp/opinion-workbench-baseline.FrBvdA/spec.md (same originating spec)
Review includes tracked and untracked implementation, including renamed backend module tree. No implementation commits yet; reviewed working tree against baseline, plus rename-normalized diffs for semantic changes.

## Standards

No additional blocking documented-standard or heuristic smell findings. Existing local-first and manual-resume / text-only boundaries appear preserved. Formatting-only churn is not treated as a correctness finding.

## Spec

- **R1 [P1] Development environment was not rebuilt after directory rename.** `backend/.venv/bin/fastapi` still has the old absolute shebang. Direct `backend/.venv/bin/fastapi --help` fails with exit 126 (bad interpreter); `mise x -- uv run --locked pytest ...` falls through to an unrelated Miniforge pytest and fails to import the new package (6 collection errors). `uv run --locked python -m pytest` passes 116 tests / 2 skipped, confirming a launcher/environment fault rather than those product tests failing. Recreate the local environment, inspect all executable entrypoints for stale paths, and verify the documented FastAPI and pytest commands work under the new directory without PYTHONPATH or old-path compatibility. Fix attempts: 0.
- **R2 [P1] Current portable upgrade instructions contradict the agreed fresh cutover and include a data-loss claim.** `windows/README.md` says extracting a new folder preserves data and deleting the program directory does not delete user data despite data living inside that folder; its checklist still instructs copying old data. `macos/README.txt` and the Release body unconditionally say copy/keep old data, without distinguishing this breaking fresh-start release. This may import old credentials/browser state into the new blank database. Synchronize current Windows/Mac bundled and root instructions and Release notes: this cutover does not import old data, old material must remain separately preserved, deleting a used portable folder deletes its nested data. If describing future same-product upgrades, clearly distinguish them from the current cutover. Fix attempts: 0.
- **R3 [P2] New source-root test is platform-dependent but unconditional.** `test_source_checkout_uses_a_namespaced_runtime_root` asserts a `runtime/opinion-workbench` suffix on Windows, where the production path intentionally is LOCALAPPDATA/OpinionWorkbench. Make the macOS/source assertion platform-appropriate and cover the Windows branch with an existing safe platform/path seam or a native test; do not change production Windows behavior merely to satisfy the test. Fix attempts: 0.
- **R4 [P2] Key new acceptance scenarios lack reproducible regression coverage.** Existing two-stage tests were adapted to create rules, but do not exercise cross-object/batch report selection with operator instructions explicitly preserved, or assert neutral defaults. The old-data isolation check is described only as a one-off, with no checked-in reproduction. Add bounded tests at existing API/execution seams for neutral defaults and operator-owned two-stage instructions, plus synthetic old-data preservation/new-state isolation. Run the final Mac ZIP's extracted `启动.command`, not only the pre-archive build executable (the implementation record currently cites only that executable), and record exact evidence. Fix attempts: 0.

## Evidence and deferred delivery

- Remote confirmed: git@github.com:jonathanhu237/opinion-workbench.git; GitHub API confirms renamed repo.
- `git diff --check` passed.
- Parent `uv run --locked python -m pytest` targeted run: 116 passed, 2 skipped (9.83 s), log /tmp/opinion-review-python-targeted.log.
- Entry-point failure logs: /tmp/opinion-fastapi-check.log, /tmp/opinion-review-targeted.log.
- Windows native build/new Release remain pending intentionally until code review passes; not marked complete and not a code-fix finding yet.
- Empty old cwd contains only .agent-relocation to allow the parent session's bash tools to execute. This is not an application compatibility link and will be removed when the session work ends.

Summary: Standards 0 blocking findings; Spec 4 findings, worst P1. Next: fresh Luna implementation invocation, first fix attempt for R1–R4.
