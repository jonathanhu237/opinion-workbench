# Run 47 Follow-up — 2026-08-28

## Implementation authority and boundary

This records the implementation-stage boundary. After the fix and verification, the user
explicitly requested commit/push; `run47-delivery.md` records that subsequent scoped authority.

After the successful Xiaohongshu recovery, the user asked why Toutiao failed and requested that
this problem be solved. Reopen the existing Toutiao repair task for a narrowly evidenced
follow-up. Its earlier repair and Git approval are historical, not authority for new delivery.
Preserve all manual-recovery and unrelated dirty changes. Main owns live browser/data, docs/specs,
source-only synchronization, remote execution and Git.

Batch 8 is terminal with failures. Immutable Toutiao run 47 stopped with `structure_changed`,
six completed terms and seven retained results. Its unconfirmed seventh query is the diagnostic
target. All other platforms succeeded and must not rerun. The stored error does not identify a
specific DOM/normalization cause.

## Ordered investigation and change boundary

1. Main opens one owned official page for the failed term and inspects rendered DOM predicates
   and counts. Preserve user tabs; no private requests, raw dumps, credentials/profile reads,
   login/CAPTCHA actions, or retry on a restriction.
2. The implementer traces current Toutiao extraction, normalization and tests read-only in parallel.
   Identify how this state differs from results, explicit empty, pending, malformed or external-only
   results. Report first; do not patch without demonstrated evidence.
3. Before product edits, record the precise gap and smallest fix. Expected scope is the existing
   Toutiao client/parser tests, plus normalization only if evidence requires it. No allowlist
   expansion, external-result following, protocol/database/UI changes, search retries or speculative
   wait-budget increases. Preserve dirty search-v2/completion/manual-page behavior.
4. Add a synthetic privacy-safe regression first; main proves red against unchanged source on
   Centaurus. Implement the narrow fix and check near-misses/safety. Run focused and complete
   derivative regressions and affected backend checks on the isolated source-only snapshot with
   the existing verified test browser. Additional tools use mise. Private runtime stays local.
5. Main may perform one bounded one-term product verification before/after the fix, cap five
   retained results. After a fresh private backup, a task-labelled temporary rule may be used only
   for this repair test; remove that rule after terminal completion and preserve run history.
   Formal rule 1 and original batch/run snapshots remain unchanged. Do not continue all 14
   remaining Toutiao terms, rerun other platforms, or call models. Browser-only inspection is not
   product acceptance, and an unreproduced historical cause remains unknown.

Earlier acceptance criteria describe the completed first repair. Record follow-up observations,
red/green evidence and actual outcomes separately. No current root cause, fix, successful replay,
new user approval message, Git commit/push or task archive is claimed at planning time.

## Observed defect and narrow repair contract

On the single owned official page for run 47's seventh term, the unchanged exact production DOM
script returned: trusted origin, one visible main container, zero candidates, `empty=false`,
`challenge=false`, and `mandatory_login=false`. DOM inspection found nine visible human-title
anchors inside `.cs-header`; every title had one ordinary official search-jump wrapper pointing
to an external HTTP(S) destination. A single visible `.cs-pagination` was inside the main result
column, with no visible loading indicator. Related-search anchors also existed in the main column,
but were not result-title headers. A follow-up count found one additional visible anchorless
`.cs-header.cs-header-with-fb` with the exact text `相关搜索`. Exclude only this known auxiliary
heading; do not generalize to ignoring arbitrary malformed headers. No external destination was visited; no URL token, publisher
identity, raw HTML, browser storage or full page dump is retained here.

This mature state deterministically exhausts the current client into `structure_changed`: it has
neither allowlisted content candidates nor the explicit no-results text. This demonstrates an
external-only-result handling defect on the failed query today, not proof of run 47's uncaptured
historical DOM. It is not current evidence of a login wall or CAPTCHA.

Add a distinct, strict external-only completion predicate instead of treating any absent candidate
as empty. Require exactly one visible main column, observed visible title-header structure with
safe external targets only, one visible main pagination control, and no visible loading or
unknown/malformed/official-title evidence. Do not count sidebar or related-search links as titles.
Keep the existing 21-read budget: only accept external-only completion at the final read, allowing
later official content to win. Return zero collected Toutiao items without following external
links or expanding the platform allowlist. Unknown pages and safety blocks keep their failures.

The internal field is `external_only_complete: bool`; every eligible title must start with an
official `so`/`sou` jump wrapper and unwrap at most twice. Direct external title links remain
ineligible. The known exact related-search heading is excluded from eligible result headers, while
all other missing/unknown titles veto completion. Strict flag shape is checked at the client.

The implementer is adding synthetic tests first in the existing parser test file. Main will prove
red remotely before authorizing the two-file source fix. Existing dirty v2 completion callbacks
must remain intact. No real product run, source fix or successful regression is yet claimed.
