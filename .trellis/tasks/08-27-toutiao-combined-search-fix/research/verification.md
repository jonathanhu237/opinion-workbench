# Verification — Toutiao Readiness Repair

## Counterfactual Red Gate

Main synchronized only the new test module to Centaurus before any production client change.
Local and remote original client SHA-256 matched:
`15f61f3ae0a32f502b9cdee731324c7e07e40cdbfb09bd98e1f9a0d88d97bab8`.

Using an explicit executable Google Chrome for Testing 152.0.7977.64, these real routed synthetic
DOM cases both failed under the original code:

- `test_client_waits_for_delayed_main_results_using_real_dom[missing-main]`: the first snapshot
  correctly saw no visible main container; the client immediately raised the main-container
  structure error before the late renderer could supply a valid result.
- `test_client_waits_for_delayed_main_results_using_real_dom[empty-main]`: the first snapshot
  correctly saw one empty main container and no explicit empty marker; the client immediately
  raised the neither-results-nor-empty structure error.

Result: **2 failed**, no skipped cases, 4.75 seconds. The only warning was the existing SQLAlchemy
`declarative_base` deprecation. The fixture intercepts/fulfills its one synthetic official navigation
and aborts other routed requests, disables service workers, and retains sidebar negative controls.
Its two-second timer plus first-snapshot gate prevents a busy machine from hiding the pending state.
This proves delayed-render false failure, not the historical production run 34's cause.

## Remote Test Environment

The server initially had no detected Chromium or Playwright browser binary. Main installed
`@puppeteer/browsers` 3.2.1 through mise and downloaded its official Chrome-for-Testing stable build.
The downloader's extraction failed because system `unzip` and its optional extractor were absent.
Main then used mise-managed `extract-zip` 2.0.1 with the same browser SDK's archive download to
extract the binary into a separate test-only cache. No system browser path, production launcher,
user profile, product database or credential was modified or transferred.

Every browser-test command uses the explicit executable `TEST_CHROMIUM_EXECUTABLE`. This is a
test-module-only override; the production `BrowserLauncher` remains unchanged.

## Backend Regression

Before the derivative patch, the unchanged backend passed on Centaurus:

- `uv run --frozen ruff check .`
- `uv run --frozen ruff format --check .`: 47 files already formatted.
- `uv run --frozen python -m pytest -q -ra tests`: **353 passed** in 5.71 seconds.

The backend has no planned code change; these checks protect the existing API/lifecycle/storage
boundary and are not a substitute for post-patch derivative or live validation.

## Patched Remote Gates

The first patched focused run was **75 passed, 2 failed**. Both delayed cases reached candidate
assertions successfully but failed on Chinese text decoding because the synthetic HTML response
omitted a charset. Only the new fixture's response content type changed to
`text/html; charset=utf-8`; production parsing did not change. The original red failures occurred
earlier, at the client's structure checks, so that readiness evidence remains valid.

After the fixture correction:

- Focused parser suite: **77 passed**, zero skips, 7.33 seconds.
- Full maintained derivative `tests/`: **589 passed**, zero skips, 15.89 seconds.
- After applying formatting-only wrapping locally and resynchronizing the exact files, format
  check passed for both files and the full suite passed again: **589 passed**, zero skips,
  15.86 seconds. Browser fixtures actually executed. The only warning in these runs was the
  existing SQLAlchemy deprecation noted above.
- Post-patch backend gate: Ruff check passed; 47 files already formatted; **353 tests passed**,
  zero skips, 5.66 seconds. No backend source was modified.

An additional Ruff check of the two derivative files reports five existing findings: two UP009
encoding declarations and three ISC004 concatenations in old fixtures. Streaming each original
HEAD file to the same remote checker confirmed the identical five findings before this task.
There are no new diagnostics. Do not describe this supplemental legacy check as fully clean or
silently remove unrelated inherited header/fixture lines.

## Live Gates

The independent code review found no behavioral defects. Combined/repeat/baseline outcomes,
temporary-rule cleanup and history/tab preservation checks passed; exact evidence is recorded in
`live-acceptance.md`. The idle owned backend was gracefully stopped only after all existing runs,
batches and batch items were confirmed terminal, to load the changed derivative client.
The new backend started successfully; exact client/test SHA-256 values match Centaurus's tested
copies. Run 44 initially waited at Chrome's repeated remote-debugging authorization, before any
term progress. Computer Use confirmed the ordinary prompt and accepted it under the user's
previous explicit permission to control this same Chrome session and click this prompt. No new
security setting, authentication credential, platform login or CAPTCHA action was performed.

Final tested source SHA-256 values (identical locally and on Centaurus):

- Client: `888f3dd3c9099d992c41048d826a9098c3e906abd8df30abe27908a75126bd8e`.
- Tests: `b9732c114dc77efea6ada8fafae660b8f3ac781b2ffb7883c7da7cf92db5c2cb`.

Both task context manifests validate; root and derivative `git diff --check` pass. Independent
static review and final evidence reconciliation passed; see `check.md`, including the inherited
lint baseline exception and historical-cause limitation. No code changes remain pending.
Implementation ended without Git delivery. The user's subsequent explicit `提交推送` request
authorizes scoped commit/push; archival remains deferred. See `implement.md` for the delivery plan.
