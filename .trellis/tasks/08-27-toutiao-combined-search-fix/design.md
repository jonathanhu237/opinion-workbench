# Toutiao Combined Search Repair Design

## Later run-47 investigation

The original readiness design below remains implemented. For the newly requested repair, follow
`research/run47-followup-plan.md`: identify the rendered-page/normalization predicate first,
then record the smallest demonstrated change. Do not assume a timeout increase or selector
expansion is justified. Preserve current search-v2/manual-recovery contracts and dirty work.

The new owned-page observation has now demonstrated a mature external-only main result column:
nine safe external title headers, main pagination, no loading/challenge/login, and zero recognized
Toutiao candidates. The follow-up plan defines a strict external-only completion exception at the
last readiness read. This supersedes only the older blanket external-only failure below; unknown
or unproven zero-candidate states must still fail. Test red before modifying production code.

The user subsequently authorized commit and push for this follow-up. Stage the two-file repair
without the three unrelated search-v2 callback test additions, and only the three Toutiao hunks
from the shared product-search spec. Validate that exact clean candidate against committed v1,
not just the mixed development workspace. See `research/run47-delivery.md`.

## Boundary and Evidence

The failure label is ambiguous. The unmodified current product run 43 succeeded with two items;
the exact existing DOM script on the owned mature page also returned two candidates. Do not invent
a selector/root-link defect or claim that historical run 34's cause is proven.

The independently testable gap is in `ToutiaoWebClient.search`: it reads once after 1.5 seconds and
rejects a still-pending DOM. Add a regression for delayed rendering before changing production code.
If the regression cannot demonstrate the failure, stop instead of implementing a speculative fix.

Expected source ownership is limited to the derivative's `media_platform/toutiao/client.py` and
`tests/test_toutiao_parser.py`. Existing product worker/lifecycle tests are regression gates; do not
change the API, database, protocol, frontend or other platform adapters. The main session owns
task/spec docs, runtime, synchronization and live operations.

## Readiness Contract

- Retain the single official navigation, response 403/429 check and initial 1,500 ms wait.
- Evaluate the same DOM snapshot, rechecking trusted origin before and after each read.
- Only two coherent pending states may be reread: zero visible main containers with an empty
  candidate list and no explicit empty marker; or one visible main container with no candidates
  and no explicit empty marker. They must still have valid expected value shapes.
- Allow at most 20 additional checks separated by 250 ms: 21 total snapshots, nominal 6.5 seconds
  of waits including the existing initial delay. Bound by count, not an unbounded retry loop.
- Recognized results/empty return immediately. Login/challenge, malformed snapshots, unsafe
  origins and ambiguous multiple containers stop immediately. HTTP blocking remains before DOM.
- Exhausted pending state keeps the existing `ToutiaoStructureChangedError` outcome. Do not treat
  absent or external-only candidates as proof of an empty search.
- All waits remain awaitable so cancellation propagates. Never catch navigation aborts, add
  private requests, reload, generate signatures or broaden main-column/URL/card extraction.

This is DOM readiness polling for the same page, not search/navigation retry. No generic polling
framework, new setting, diagnostic payload, saved page dump or public error code is needed.

## Validation and Compatibility

Use synthetic fixtures and existing browser detection for offline DOM tests on Centaurus. A
delayed-render test should execute the real snapshot script under a routed, synthetic official
page with no outbound requests. Prove it fails against the old client and passes with the patch.
Mocked state sequences cover exact read/wait limits, eventual explicit empty, permanent pending,
immediate invalid/challenge/login, changed origin between checks and cancellation.

Retain all existing parser title/identity/card/empty/main scoping and normalization tests. Run the
maintained derivative `tests/` suite and backend regression suite remotely. Browser fixtures must
actually execute, not be silently skipped because Chromium is missing.

For live acceptance use the existing application and formal history, not a substitute browser.
Back up locally first. Temporary task rule 5 is restricted to the current single locality/issue,
then may be replaced with that locality alone for one baseline; delete it after terminal checks.
Do not alter formal rule 1. Preserve all existing rows, first-seen identities and earlier failed
attempts. Stop for blockers. Recycle only the owned idle backend/worker if needed to load code.
Keep user Chrome open and all pre-existing tabs. Credentials and backup never leave the Mac.

## Delivery and Deferred Work

User delegated this task's approval explicitly; after this written plan, activate and dispatch
implementation without fabricating a new user message. Git delivery was initially deferred; the
subsequent explicit `提交推送` request now authorizes scoped commits and pushes on existing `main`.
Push the derivative first, verify its clean reachable revision and fresh recursive clone, then
commit/push the parent pointer with task/spec evidence. Preserve unrelated work; do not archive.
Publication-time sorting remains a separate requested follow-up, not implemented here.
