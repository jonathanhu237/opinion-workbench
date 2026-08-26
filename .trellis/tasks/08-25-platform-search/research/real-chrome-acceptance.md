# Real Chrome / Toutiao acceptance

- Date: 2026-08-26 (Asia/Shanghai)
- Scope: approved local Chrome debugging session, one enabled five-term monitoring-rule snapshot,
  Toutiao only
- Retained evidence: outcome categories and aggregate counts only; no cookies, profile paths, raw page
  content, user tab inventory, child frames, or credentials

## Browser connection and login behavior

Recycling the pre-fix persistent worker correctly invalidated the prior debugging connection. The
next operation ended as `browser_unavailable` without writing content. The user then visibly approved
Chrome remote debugging again. The account check reported that Toutiao was not logged in, but the
official public search page remained available. Search therefore proceeded without treating login as
an unconditional precondition. No login wall, CAPTCHA, slider, retry, bypass, private API, or fallback
browser appeared during the accepted runs.

This live result refines the product contract: borrow the approved Chrome session for search, but
require login only if Toutiao actually presents a mandatory login wall.

## Main-result parsing correction

The first pre-fix acceptance exposed that a whole-page anchor scan selected the PC search page's
right-side hot board before the keyword result column. Live visible-DOM inspection established a
single `.s-result-list` main column and a distinct `.s-side-list` hot-board column. The adapter was
corrected to require exactly one visible main column, group duplicate anchors by content identity,
prefer the human title anchor over duration/image/detail labels, and fail as `structure_changed` when
the main column is missing or ambiguous. Offline DOM fixtures and the maintained MediaCrawler suite
passed before rerunning live acceptance.

Only the invalid test runs/content created by the pre-fix parser and one connection-failure run were
removed. Monitoring rules and unrelated runtime data were untouched. SQLite foreign-key integrity
was clean after cleanup.

## Accepted runs and deduplication

The first accepted run used a per-term limit of three and completed with:

- 13 unique normalized contents;
- 13 `new` run associations and zero `repeated` associations;
- official Toutiao content links with recognized content identities;
- visible progress, a terminal completed state, and matched-term provenance;
- no unrelated hot-board entries.

The immediately repeated run completed with:

- zero new contents and 13 repeated associations;
- the global content table still containing exactly 13 rows;
- all 13 contents retaining their original `first_seen_at` and receiving a later `last_seen_at`;
- every content identity associated with both completed runs;
- repeated labels and counts matching the SQLite projection.

`PRAGMA foreign_key_check` returned no rows after both runs.

## Cancellation and borrowed-page ownership

A bounded run was cancelled through the visible task page and reached the terminal `cancelled` state.
Partial results followed the documented retention rule. For the ownership sentinel, a temporary
`https://example.com/` tab titled `Example Domain` was created before another bounded cancel test.
Its tab identity, URL, and title were unchanged after cancellation, proving that task cleanup did not
close or navigate the sentinel. The temporary sentinel was then closed explicitly.

The API health endpoint remained healthy after completion, repetition, and cancellation, and the
persistent worker remained available.

## Privacy and protocol scan

- Worker process arguments contained only the fixed `python -m tools.auth_worker` command; monitored
  terms were not present in argv.
- Search-run list responses contained only the documented summary keys and terminal statuses.
- Parent and derivative diffs contained no credential values, profile paths, raw page/child frames,
  cookies, authorization headers, or unmasked identity payloads. Matches for `password` were URL
  validation checks that reject embedded credentials.
- Parent and derivative `git diff --check` passed.
- No raw browser/page response was written to this evidence file.

## Full user-visible UI matrix

After the core live runs, every currently implemented collection-run path was exercised again:

- history listed completed and cancelled runs newest-first with matching new/repeated counts;
- starting without a rule produced the inline rule-selection alert and created no run;
- per-term values `0` and `51` produced the exact lower/upper-bound alerts and created no run;
- the first-run `new` tab showed all 13 records and its zero-count `repeated` tab showed the honest
  empty state;
- a direct repeated-result deep link selected the `repeated` tab after navigation/refresh, showed all
  13 records, and the zero-count `new` tab showed the honest empty state;
- a zero-result cancelled run and a partial-result cancelled run both retained their truthful
  guidance and counts;
- a missing run ID rendered the stable recovery UI instead of crashing;
- original links used `_blank` plus `noreferrer`; one representative official Toutiao article was
  actually opened and resolved to the expected official article page;
- list/detail pages had no document-level horizontal overflow at widths 375, 768, 1024, and 1440;
  the mobile navigation opened and closed after route selection;
- the browser console contained no warnings or errors after the matrix.

The matrix did not launch an artificial 50-result-per-term live search because that would add
platform load without increasing boundary confidence; the valid hard maximum and worker enforcement
remain covered by automated tests.
