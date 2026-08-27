# Run 47 Follow-up Delivery — 2026-08-28

## Current authority and scope

The user explicitly requested `好的，请你 commit 并 push 吧。` after the completed repair and live
verification. Deliver on the existing `main` branches, derivative first and parent second. Do not
create a PR/branch, archive the task, rerun platforms or include the other ongoing work.

Starting parent/remote HEAD is `12df65d992240a60e4eae6f6ba83e2fb2562017d`; derivative/remote HEAD
is `8a7b620628d7447f05cf565a446eae31779f576a`. Both indexes were empty. Dirty paths were inspected
before staging. Independent Trellis review confirmed the new internal DOM predicate works with
the committed search-v1 worker and does not depend on the uncommitted manual-recovery feature.

## Commit groups and exclusions

1. `fix(toutiao): handle completed external-only search results`
   - `media_platform/toutiao/client.py`.
   - Only current repair changes in `tests/test_toutiao_parser.py`; leave its three preexisting
     `emit_term_completed` callback additions unstaged.
2. `fix(search): pin Toutiao external-only result repair`
   - Reachable derivative gitlink, browser-search adapter spec and this task's follow-up records.
   - Only three Toutiao hunks in the shared product-search spec: predicate, empty-result matrix,
     regression requirements. Leave all v10/search-v2/checkpoint/manual-page changes unstaged.

All other manual-recovery, AI configuration, placeholder and frontend work stays uncommitted.
Private runtime, backup, credentials, browser profiles and raw page dumps are excluded.

## Exact-candidate validation and preservation plan

The preceding 655/408 results describe the mixed development workspace. Export the exact staged
derivative tree into a new source-only candidate, rsync it to a new isolated Centaurus directory,
and run the maintained suite there with the verified test browser. Validate the committed-parent
candidate separately; do not substitute the mixed workspace gate.

Before the parent pointer commit, temporarily preserve only the remaining derivative changes in
a uniquely identified local Git stash, after checking no active product operation. This permits
the required clean-submodule check without discarding or committing that work. Keep its immutable
stash object and baseline file hashes; restore it immediately after the parent commit and verify
all file contents and untracked files. No unrelated parent files or existing stash entries are
modified. Clone the exact prospective parent commit locally and initialize the public HTTPS
submodule to prove reachability and clean reproducibility.

## Checkpoints

- [x] Scope and exact hunk exclusions independently reviewed; remote tips unchanged.
- [x] Exact staged candidate regression and scoped lint/format comparison passed.
- [x] Derivative committed and pushed; remote tip verified.
- [x] Parent candidate recursively initialized with the exact clean reachable derivative.
- Parent commit/push and exact unrelated-work restoration are verified immediately after the
  commit; their final commit IDs are reported from Git, not embedded self-referentially here.

## Exact candidate results

Source-only exports were validated at `/tmp/longtian-toutiao-delivery.SEZJ8g` on Centaurus:

- Derivative maintained suite: **610 passed**, 19.58 seconds, zero skips and one inherited
  SQLAlchemy deprecation warning. This includes the repair on committed search v1, not the other
  development changes.
- Committed-parent backend suite: **353 passed**, 6.05 seconds.
- Both edited derivative files pass formatting; the same five inherited Ruff findings remain
  (two coding headers, three old fixture concatenations), with no introduced lint finding.
- Scoped staged whitespace checks passed in both repositories; credential-pattern scans found no
  key/token/private-key values in the derivative diff.
- Exact candidate SHA-256: client `74c4a85b158295d432ee12f2a076f6477db6c0c7f6ee3443ce08b9c6128289a3`,
  parser tests `b0def5f2f653739c181b55a5bf0f2c8874f8cdc9156f92944c942f298b4a2080`.

Derivative commit `c56d37559af234c3af298167bd53995c74f04f0e` was pushed to `origin/main`,
advancing `8a7b620`. Its tree is the exact validated index tree
`c0a0cfaea8ca7d740ec3a91f078cdc55fe31e0ef`. Parent reproducibility and publication follow below;
the mixed working tree remains intentionally dirty with unrelated work.

## Reproducibility checkpoint

The prospective parent candidate was cloned locally into a new temporary checkout. Recursive
initialization fetched the dependency from its configured public HTTPS URL and checked out exactly
`c56d37559af234c3af298167bd53995c74f04f0e`; the parent index uses mode `160000`. Both fresh parent
and nested worktrees were clean and `git submodule status --recursive` matched. The subsequently
added delivery checkpoint text changes only documentation, not the validated source or gitlink.

No product operation was active before the short clean-submodule commit window. No runtime or
credential files enter the stash, candidate export or Git index. Existing untracked derivative
source is included in the temporary preservation, and all remaining file hashes/status are checked
after restore. The task remains unarchived and all other parent work remains outside this commit.
