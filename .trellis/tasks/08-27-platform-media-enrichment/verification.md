# Media Enrichment Verification

## Approval and isolation — 2026-08-28

The user replied `来` to the final post-probe scope review. This child was activated
with `task.py start`; the summary child is approved but waits for the media checks.
Implementation uses separate fork/backend owners and a shared versioned contract.

All edits and Git operations remain local. Main prepared the isolated Centaurus
checkout `/tmp/longtian-media-validation.DeYMEC`, copying local tracked/untracked
source only with ignored runtime, environment files, browser data and credentials
excluded. Existing managed backend/fork environments are linked, not copied or
reinstalled. No production service or database was changed by baseline verification.

## Baseline before new enrichment integration

- Backend full suite: **408 passed in 8.54s**; Ruff check and format check passed
  (51 files formatted). This is the existing application baseline, not the new
  feature's final gate.
- Fork regression subset: **342 passed in 11.35s**. Paths: product_search,
  product_search_recovery, five-platform product-search tests (Toutiao through
  test_toutiao_parser), auth_worker, auth_worker_protocol, auth_protocol and
  cdp_browser. One pre-existing SQLAlchemy declarative_base deprecation warning.
  This is a named subset, not the entire derivative suite.
- A separate full-fork baseline rerun completed with **655 passed in 18.37s**,
  with the same existing SQLAlchemy warning. This snapshot predates the new fork
  enrichment implementation; it is not the feature's final fork gate.
- Offline DOM tests use the installed Chromium 1234 through the existing
  `TEST_CHROMIUM_EXECUTABLE` override. The environment's default Playwright path
  points at an unavailable 1228 installation, so it was not used.
- `mise x ffmpeg@9.0.1 -- ffprobe -version` succeeds on Centaurus. No dependency
  installation or conversion was performed.

## Implementation checkpoints (historical)

Initial implementation snapshot: backend **429 passed, 3 failed in 8.61s**.
Two new source-fixture cases called the existing keyword-only `observe_item`
positionally; the backend owner is correcting the fixture. The third failure was
the shared golden JSON missing from the isolated fork snapshot, subsequently
copied explicitly. No final feature gate is claimed from this run; source/tests
continue changing. The separately started full-fork baseline output was lost at a
context boundary and is not counted as a verified result.

The next frozen backend snapshot passed **460 tests in 8.66s**, Ruff check and
format check (58 files). Independent review subsequently found a directory
allocation/fsync failure cleanup gap; its fix and regression test are pending a
fresh gate. This passing snapshot therefore is not final sign-off.

After the narrow allocation rollback fix and two regression cases, backend gate
passed **462 tests in 8.59s**, Ruff check and format check (58 files). Fork integration
and cross-side final review still remain; passing backend tests alone do not prove
actual acquisition or complete the child.

A read-only query of existing result metadata identified possible later live
targets (run/source): DY 50/378, KS 49/353, Toutiao 47/143, WB 48/173,
XHS image 52/492 and video 52/482. These are terminal-run candidates, not verified
full-media fixtures. The query did not retrieve credentials, signed media URLs or
raw post text, and made no browser/provider request.

First joint implementation snapshots passed the four new fork shared suites
(`protocol/io/projection/worker`): **108 passed in 1.06s**, and the three new
platform suites (`weibo/kuaishou/xhs`): **91 passed in 2.45s**. The latter used
installed Chromium, with no skipped browser fixtures. Both had only the existing
SQLAlchemy warning. Backend enrichment suites also passed **54 in 0.35s** against
the newly synchronized golden corpus. Further narrow review fixes and final full
regression are still required; none of these synthetic tests is live acceptance.

## Final offline checkpoint — 2026-08-28

- Full backend: **462 passed in 8.94s**, Ruff check/format clean (58 files).
- Full fork after the final import-only normalization: **867 passed in 20.19s**,
  no skips, only the existing SQLAlchemy deprecation warning. Earlier full run was
  also867 passed in20.36s.
- Fork checks run from the fork root using explicit isolated Ruff settings:
  `ruff check --isolated --select E4,E7,E9,F,I` and
  `ruff format --isolated --check` on the16 owned Python files. Both passed.
  The first non-isolated run found10 I001 differences because local/remote working
  directories inferred different first-party imports; owners fixed imports only.
- `verification/offline_probe.py` exercised the real ffprobe9.0.1 process using
  generated media, not a mock: H264/AAC MP4,6973 bytes,64x64,1065ms, audio present;
  a generated silent MP4 returned `audio_missing`. Both operation directories were
  empty after cleanup. No platform, private file or provider input was used.
- The managed ffprobe executable is0775 and was correctly rejected by the safety
  guard. Copying only that dynamic binary loses its `$ORIGIN/../lib` dependencies.
  Validation used a0700 binary copy under the isolated checkout's `ffmpeg/bin`,
  with `ffmpeg/lib` linked to the already installed library directory, supplied by
  the trusted absolute `MEDIACRAWLER_FFPROBE` override. System tool permissions and
  production configuration were not changed. Deployment must satisfy this runtime
  prerequisite rather than assuming any PATH executable is accepted.

This was an offline foundation checkpoint, **not completed platform-media support**.
At that checkpoint CDN allowlists were empty. DY/Toutiao explicitly returned `structure_changed` pending
real detail-page evidence. WB long text/video inventory and KS success/inventory
semantics remain incomplete; XHS uses the bounded first-page/exact-note path, but
its actual media has not passed live validation. No summary API, model call or UI
was added in this child, and the summary dependency remains unfulfilled.

Normal terminal/cancel paths settle owned probe/thread work. Abnormal worker death
only proves writer exit; a read-only ffprobe may outlive it because its timeout was
enforced by the worker coroutine. Whole-group reaping/zero-orphan behavior is an
explicit unresolved resource limitation, not an established guarantee. No global
process-manager change was made to hide or broaden this boundary.

## Acceptance status

- [x] Exact fork/backend protocol and normalized content contract agree in fixtures.
- [x] Safe downloader/prober/staging/manifest/path/size/hash fixtures pass.
- [x] Five-platform projection fixtures cover identity, supported text/media candidates
  and explicit incomplete/unavailable cases; this is not live-support acceptance.
- [x] Normal browser ownership/cancellation and current manual-recovery regressions pass.
- [x] Full backend/fork regression and scoped lint/format pass.
- [ ] Entire child implementation and live-platform acceptance receive final sign-off.
- [ ] Authorized live exact-source verification establishes each claimed platform
  and modality; no unavailable-only or fixture-only support claim.
- [x] Source history, credentials, user tabs and existing runtime are preserved.

Local-browser readiness was requested asynchronously while code/fake checks continue.
No fresh browser or provider request is claimed by this verification record. The
three-video experiment belongs to the earlier acceptance task and is not reused as
product cache or this feature's live acceptance.

No archive, commit or push was performed. The child remains `in_progress` and the
approved summary child waits. The browser-readiness request above was subsequently
approved; the following section supersedes that next-action note.

## Approved browser and real-file increment — 2026-08-28

The user's `好的` approved opening a few stored originals in the current Chrome
browser, without an AI call. See `research/live-dom-observations.md` for sanitized
per-platform DOM/identity evidence and the exact new implementation boundaries.

- DY: exact-ID caption/player regions observed. A production downloader/staging/
  ffprobe check of its actual video succeeded: 4,432,193 bytes, MP4,576×1024,
  15,100ms, audio present; temporary operation empty and root removed afterward.
- Toutiao: the stored HTTP legacy article redirected to the same-ID HTTPS article.
  Scoped body,8 actual lazy-image locators and an embedded video were observed.
  One actual image passed production file validation:568,274 bytes,JPEG,1920×1080,
  with complete temporary cleanup. The full article's remaining media was not
  downloaded; a single-image proof does not establish complete-source acceptance.
- Kuaishou: the stored video played normally after clicking its visible play
  control. Actual source and player metadata were observed; file bytes, existing
  API success/completeness semantics and full handoff remain unverified.
- Weibo: original text and a loaded post image were visible. An empty page-level
  video also existed; media inventory completeness must remain unproven.
- XHS: one direct stored image URL reached official300031 (`当前笔记暂时无法浏览`).
  No reload, challenge action or alternate-source fallback. The separate product
  first-page/exact-ID reopening path was not tested by this direct visit.

Main's `verification/live_asset_probe.py` accepts the observed locator only on
private stdin and reuses production guards. It does not control a browser, read the
DB, call a provider, persist a locator or send credentials. The unsafe-loopback
input test and scoped Ruff checks passed on Centaurus; real file checks used the
existing local ffprobe8.1.2 and did not perform conversion or remote media transfer.

Only the owned audit tab was explicitly closed. One baseline tab was already absent
before cleanup and the other remained; the cause is unobserved. Consequently this
is **not** a passed two-tab live sentinel/cancellation gate. No main action targeted
the original tabs and no attempt was made to restore a possibly user-closed tab.

The narrow DY/TT adapters and paired legacy-URL compatibility are implemented
against these observations. Current host additions are exact and observed, not
wildcards. Their new synthetic regression/check checkpoint will be recorded below.
This increment does not finish whole-worker/backend live handoff, five-platform
support, summary integration or AI audiovisual acceptance. No API key was accessed,
model called, user data changed, task archived, commit created or push performed.

### Increment regression checkpoints

- DY initial focused run:68 passed,1 failure. Removing the only visible heading
  collapsed the fixture's information container; the production visibility guard
  correctly failed closed. The missing-caption fixture now keeps a visible region,
  with no guard relaxation. Rerun:69 passed,0 skipped,in3.27s.
- TT initial frozen adapter + protocol + shared projection suites:166 passed,
  0 skipped,in10.94s. Two later pseudo-element unknown-media fixtures are included
  in the final explicit product-suite gate, not in this historical count.
- Backend full suite against the paired legacy-URL/golden changes:462 passed in
  9.20s; Ruff check and format passed for58 files.
- Independent review reproduced seven false-ready XHS cases through actual
  offline JavaScript→Python→materialization. After the shape-fidelity fix,
  WB/KS/XHS plus task-only probe tests passed110 in5.70s,0 skipped.
- Scoped static checks passed for20 files:18 fork enrichment/worker/adapter/test
  files and the two task-only live-probe files. A probe-test signature needed one
  mechanical formatting correction; no runtime behavior changed.

Main accidentally used bare `pytest -q` for one broad derivative run. It included
the unrelated legacy `test/` integration directory as well as product `tests/`:
6 Redis authentication failures,8 MongoDB skips,1044 passed,4 subtests passed in
57.03s. This is **not** a passing full-repository gate. Redis failures occurred at
authentication, including before proxy retrieval; no Redis/Mongo service or
credentials were changed to make them pass. The reproducible product regression
command is explicit `pytest tests/`; its final result is recorded separately below.

### Final maintained-product checkpoint for this increment

- Explicit derivative `PYTHONPATH=. TEST_CHROMIUM_EXECUTABLE=<validated Chromium>
  .venv/bin/pytest -q tests/ --tb=short`: **1035 passed in36.97s, zero skipped**,
  only the existing SQLAlchemy deprecation warning. This includes the final TT
  pseudo-element cases and XHS positive/negative real-JavaScript assertions.
- Task-only `verification/test_live_asset_probe.py`: **10 passed in0.12s**.
- Backend final paired-contract snapshot: **462 passed in9.20s**, full backend
  Ruff check/format passed for58 files (no further backend code changed).
- Final scoped derivative/task Ruff check/format: **20 files clean**, run from the
  derivative root with isolated E4,E7,E9,F,I settings and the backend environment's
  Ruff executable. No separate type checker is configured/reported for this increment.
- Independent increment review covers all five projection seams/tests, the paired
  legacy URL validators/corpus, exact-host additions, task probe and new fidelity
  spec. L1/L2 are fixed and tested; see `research/live-media-increment-check.md`.
- Both local repositories pass `git diff --check`. No commits, gitlink publication,
  pushes, database/configuration edits or task archival were performed.

The media child remains **in_progress**. The remaining gate is not another fake
test count: whole worker→backend actual-source handoff, complete per-platform
inventory/media (especially WB/KS/XHS), and live ownership/cancellation proof still
need completion. At this media checkpoint, the summary child was still waiting;
no AI call or summary UI was added by this increment. Subsequent manual-summary
implementation and its separate offline/live acceptance boundary are recorded in
`../08-27-ai-opinion-summary/research/verification.md`. Actual media files were
removed after probing, and the remaining in-memory ephemeral media locators were
discarded at the end of this audit.
