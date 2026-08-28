# Independent Douyin Media Repair Check — 2026-08-28

## Verdict and scope

**PASS for the bounded video repair and offline integration gates.** No new
blocking code finding was identified. This is not successful real model/report
acceptance, support for Douyin image posts, or five-platform media signoff.

The existing Trellis reviewer read `check.jsonl`, PRD/design/implement, the repair
boundary and verification record, their referenced contracts, and applicable
media-projection/platform-connection/submodule guidelines. Package discovery
reported a single repository with backend/frontend/infra layers. Only the three
frozen derivative files below were reviewed as product changes. No worker
protocol, backend, UI, schema, unrelated platform, or shared ownership change was
introduced by this repair.

## Findings (fixed)

No reviewer product changes. The implementer fixed the previously identified
premature projection and exact observed CDN compatibility gap before handoff.
The reviewer wrote only this record and synchronized the three explicit source
and test paths to the existing isolated Centaurus checkout.

## Findings (not fixed)

- No remaining blocking defect was found in this scope.
- Results 125/121/122/123 were subsequently observed by the main session to
  redirect from their stored video path to same-ID note pages. Those unsupported
  image-post layouts must remain incomplete; neither the longer wait nor a
  recommended player establishes video input. No image-post implementation was
  requested or added in this repair.
- Historical summaries 1/2 made zero provider calls. Their individual worker
  failures cannot all be reconstructed from the collapsed public acquisition
  error. The real-DOM regressions prove a readiness defect, not every historical
  item's exact root cause or a background-tab throttling theory.
- Main-session source 124 download/probe evidence (2,295,446 bytes, MP4,
  20,034 ms, 720×1280, audio present, owned cleanup) is a separate lower-level
  live check. It does not prove worker-to-backend handoff, a paid model response,
  grounded audio understanding, saved analysis, or a source-linked report.

## Code and regression review

- `enrich_with_context` retains one canonical navigation. Readiness uses a
  30-second budget: up to 29 seconds of 200-ms polling, with the final second
  reserved for a fresh strict projection. It does not add a second 30-second
  projection wait. Existing navigation, download/probe, and outer worker
  deadlines remain separate and unchanged.
- Structural presence alone no longer exits readiness. A successful projection
  requires complete caption coverage, complete visible exact-source inventory,
  no projection issue and actual candidate locators. File/MIME/hash/size/audio
  verification still occurs independently before normalized input is ready.
- Source URL/type and challenge checks are outside the catch that tolerates
  transient missing/hidden DOM. Wrong-source and same-ID `/note/` redirects
  remain terminal. `CancelledError` is not swallowed by the timeout handling.
  Existing owned-page cleanup/retention is reused without activating or closing
  unrelated tabs, exporting browser state, or creating a new browser owner.
- A final partial/unknown projection remains partial/unknown. Permanent visible
  expand controls, clipping/unknown geometry, missing media and empty `currentSrc`
  cannot be promoted to complete input. No cover, recommendation, hidden-state,
  alternate endpoint, reload, or model retry was added.
- The host change adds only `v95-web-sz.douyinvod.com` alongside the existing
  `v26-weba.douyinvod.com`. Both use the same public-DNS validation, pinned IP,
  original Host/TLS SNI, no credential forwarding, no redirect, streamed byte cap,
  staging/file validation and independent audio check. Lookalike/userinfo/port/
  non-HTTPS variants remain rejected before DNS.
- New regressions execute the real `enrich_with_context` → `read_snapshot` path
  in network-disabled Chromium, separately delaying structure, information and
  caption visibility, player visibility, and `currentSrc`. Materialization is
  captured for these DOM-only tests; separate real downloader/probe boundaries
  use fake network/media responses. Deadline, cancellation, mid-poll note
  redirect, challenge retention and existing-user-page sentinels are covered.

Implementer-reported red evidence: the old adapter failed three delayed
visibility/source cases, while the structural-delay control passed. The final
focused five-suite run was **253 passed**, zero skips. These are attributed to
the implementer; the independent complete gates below were rerun by this reviewer.

## Independent verification

Checkout: `/tmp/longtian-media-validation.DeYMEC` on Centaurus. Only explicit
source/test files were synchronized; no runtime, database, credentials, profile,
media, `.git`, dependency directory or private log was copied.

From `third_party/MediaCrawler`:

```sh
TEST_CHROMIUM_EXECUTABLE=/home/jonathanhu237/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome PYTHONPATH=. .venv/bin/pytest -q tests/ --tb=short
../../backend/.venv/bin/ruff check --isolated --select E4,E7,E9,F,I media_platform/douyin/product_enrichment.py tools/product_media.py tests/test_product_media_douyin.py
../../backend/.venv/bin/ruff format --isolated --check media_platform/douyin/product_enrichment.py tools/product_media.py tests/test_product_media_douyin.py
```

- Maintained derivative suite: **1058 passed, zero skipped, 47.70s**. One existing
  SQLAlchemy `MovedIn20Warning`; no new warning or failed test.
- Scoped derivative lint and formatting: **PASS**, all three files.

From `backend`:

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
PYTHONPATH=src .venv/bin/pytest -q tests/ --tb=short
```

- Backend: **596 passed, zero skipped, 12.52s**; Ruff and formatting **PASS**,
  69 formatted files.
- Python has no separate configured type-check gate here. No frontend source
  changed, so its previously recorded gate was not rerun or claimed as fresh.
- All 70 tracked backend source/test/manifest/lock files matched local and remote
  SHA-256. The three reviewed files matched remote before tests and local again
  after completion:

| Derivative path | SHA-256 |
| --- | --- |
| `media_platform/douyin/product_enrichment.py` | `7256b8f67e69bcb82ceddb14a018137328fd88fa1ffbb83658f7cdeb17112d94` |
| `tools/product_media.py` | `08faedc72f1a24b9f978164ae578bb68389f12b0659608c716dbb3a2d72478c2` |
| `tests/test_product_media_douyin.py` | `b2147d9dc36deb6f6add6d7077764be04e202f948dfd421eb13f907405f1c1f4` |

The updated media-projection spec and repair boundary accurately preserve the
video-only, strict-completeness scope. Main owns the separately authorized live
run and its evidence. This reviewer made no live browser/platform/provider/API
request, accessed no user database or credentials, and performed no Git writes,
commit, push, deployment or archive. Submodule publication/fresh-clone delivery
checks remain for a separately authorized delivery step.

## Live handoff status (main-session evidence)

After the independent gate, main started summary **3** through the normal UI
with request `748af409-3d2b-480f-ae59-10c1a060076f`, the same five run-41 sources,
revision 1 and `force_refresh=false`. At the latest reported observation, the
restarted backend's Chrome remote-debugging authorization prompt was awaiting
the user's action-time confirmation and model attempts were zero. This is not a
terminal or successful live-acceptance result. The task remains `in_progress`;
the reviewer did not inspect or operate the prompt, poll the API, or trigger any
additional operation.

Subsequent main-session update: summary 3 was cancelled at 09:19:05 UTC while
awaiting that confirmation, with 1 input-incomplete item, 4 cancelled items,
zero provider requests/tokens and no document. The independent code-check
conclusion is unchanged; no successful real worker/model gate is claimed.

## Follow-up checkpoint: rendered caption geometry

**PASS after the independent follow-up gate below.** The preceding 1058/596 gate
and hashes describe the readiness/host checkpoint, not this new caption-geometry
implementation.

Main-session evidence for summary 4 now proves that result 124 reached the
backend as a complete MP4 asset, while its caption remained `text_incomplete`;
model attempts were still zero. The independent reviewer did not read the live
database, inspect Chrome, or issue API/model requests for this follow-up.

The approved correction is confined to the Douyin adapter and its tests:
evaluate actual nonempty descendant text ranges rather than requiring nonzero
inline heading client/scroll dimensions or equating an oversized heading font
box with clipped text. No fixed five-pixel overflow exemption, CSS mutation,
title-only fallback, new source type, or relaxed media guard is allowed.

Initial review feedback sent to main and the implementer:

- Reproduce a real zero-line-height inline H1 with smaller two-line descendant
  text; its element/scroll box overflows while every actual text range fits.
- Nonempty text nodes require finite, positive range evidence and visibility
  through their own ancestor chains. Hidden text must not disappear from
  `innerText` and thereby manufacture a complete-caption decision.
- Verify genuine horizontal/vertical clipping, line clamp, empty/unknown range
  geometry, clip/clip-path and unsupported transforms remain nonready. Compare
  actual supported clip bounds, not an unchecked border-box approximation.
- Clarify clipping ancestors above the source info node as well as intermediate
  descendants. An outer clipping container can hide text even when the info
  element itself is visible.
- Bound visited nodes (including whitespace), returned rectangles and ancestor
  depth. New synchronous DOM traversal must not rely only on the Python await
  deadline to constrain browser-side work.

No product files were edited by the reviewer. Independent synchronization and
tests began only after the implementer released the shared isolated checkout.

### Final caption-geometry findings

No remaining blocking finding was identified in this bounded correction.

- The implementer replaced the inline-client/scroll-box assumption with actual
  text-node ranges. A normal inline element's zero client dimensions are allowed,
  but its visible finite element geometry and each nonempty text node's positive
  text geometry are still required. Non-inline zero/unknown metrics remain
  unknown. Empty-width collapsed-whitespace rectangles do not replace the
  requirement for a positive rectangle on that nonempty node.
- Each text rectangle is checked against its ancestor chain through the document
  element. Clip bounds intersect client geometry with the border-adjusted box,
  excluding borders/scrollbars. Real horizontal/vertical clipping, including
  outside the exact info node, remains incomplete. No fixed overflow allowance
  or source DOM/CSS mutation was introduced.
- Hidden descendant text, clip/clip-path, unsupported transforms/independent
  translate/rotate/scale/zoom, masks/filters/paint containment and unknown
  geometry cannot produce a complete caption. The reviewer identified the need
  for an explicit line-clamp guard even when overflow is visible; the implementer
  added that guard and its real-DOM negative regression before freezing.
- Synchronous traversal has explicit limits: 2,048 visited descendant nodes
  including whitespace/non-text nodes, 2,048 range rectangles, 40,000 UTF-16
  units of descendant text and 64 ancestor levels. Exceeding any bound retains
  unknown coverage rather than returning a clipped prefix as complete.
- Existing expansion/ellipsis checks, exact source/type/note rejection, the
  single 30-second readiness budget, cancellation and owned-page cleanup remain
  unchanged. The previously checked two-host map and all download/file/audio
  guards were not changed in this follow-up.

Implementer-attributed red evidence: the 32px and 64px inline-heading fixtures
both failed the old `caption_clipped` assertion, **2 failed in 1.95s**, after
proving that their real descendant text ranges fit the clip parent. Earlier
fixture-construction adjustments are not counted as product red evidence.
The implementer's final focused gate was **123 passed, zero skipped, 30.97s**.

The new tests include real-DOM positive inline/font-box cases, actual padding
clip versus border-box behavior, 18 adverse layout cases, unknown range cases
and traversal limits. An orchestration regression runs the real
`enrich_with_context`/readiness/snapshot path, verifies one navigation and one
materializer invocation, and closes only the owned page. That test captures
materialization with a fake boundary; it is not a real download or model call.

### Independent caption-geometry verification

Only the final adapter and its test file were synchronized from local source to
`/tmp/longtian-media-validation.DeYMEC`; no runtime, profile, database, credential
or media was copied. From its `third_party/MediaCrawler` directory:

```sh
TEST_CHROMIUM_EXECUTABLE=/home/jonathanhu237/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome PYTHONPATH=. .venv/bin/pytest -q tests/ --tb=short
../../backend/.venv/bin/ruff check --isolated --select E4,E7,E9,F,I media_platform/douyin/product_enrichment.py tests/test_product_media_douyin.py
../../backend/.venv/bin/ruff format --isolated --check media_platform/douyin/product_enrichment.py tests/test_product_media_douyin.py
```

- Full maintained derivative suite: **1089 passed, zero skipped, 64.61s**; only
  the existing SQLAlchemy `MovedIn20Warning`.
- Scoped lint/format: **PASS**, both changed files. Local scoped `git diff
  --check` also passed; this was read-only and performed no Git mutation.
- Local hashes matched the remote tested hashes and remained unchanged after
  the gate:

| Derivative path | SHA-256 |
| --- | --- |
| `media_platform/douyin/product_enrichment.py` | `8a027d32763047a41ce125420f7e953c96f9dfadb8511cff37280611d101dcb7` |
| `tests/test_product_media_douyin.py` | `fc0dafe5fe874a73c698f198b702b5289eacccbbe9023aaf6105920c4b3dd4cb` |

The unchanged media helper remains
`08faedc72f1a24b9f978164ae578bb68389f12b0659608c716dbb3a2d72478c2`.
Backend/frontend source did not change; their earlier evidence was not rerun or
claimed as a fresh gate. No separate Python type-check command is configured.

This follow-up proves the bounded code/fixture correction, not universal CSS
layout support or a successful real report. Unsupported geometry and the four
note sources still remain incomplete. Main owns the next authorized live
acceptance and its results; the reviewer made no live browser/platform/API/model
request and did not alter local runtime or Git state.

## Final phase 2.2 checkpoint: bounded legacy-clamp proof

**PASS for this frozen code/fixture scope.** This gate supersedes the earlier
1089-test caption checkpoint for the two changed files. It does not establish
successful real worker/model/report acceptance. Main's latest recorded summary
5 still had five incomplete inputs and zero provider requests; the reviewer did
not access that runtime or trigger a further operation.

The reviewer followed the `trellis-check` artifact/spec and quality-check
sequence. Only the final Douyin adapter and its dedicated tests were synchronized
to the existing isolated Centaurus checkout, after the implementer released it.
No product changes were needed during this independent final pass.

### Findings resolved in the implementer's frozen patch

- A configured direct-parent legacy clamp can now pass only with bounded
  positive geometry for every non-whitespace Unicode character. Actual text
  parents must share one finite positive line height; ordinary inline H1 zero
  line-height and inert vertical margins do not substitute for that evidence.
  Character rectangles must fit both every clipping ancestor and their line
  slot below the configured clamp limit. A third line remains incomplete even
  inside an explicitly enlarged 130px container.
- The proof is confined to the exact caption's direct clamping parent and
  ordinary inline SPAN/A descendants. Additional nonhidden siblings, BR/block
  flow, shifted positions, mixed/unknown line height, unsupported higher clamps,
  hidden text and missing/nonfinite/zero character geometry cannot become
  complete. Existing source/type, expansion/ellipsis and unknown-inventory
  guards remain in force.
- Generated content is checked on the direct clamp, H1 and all SPAN/A nodes,
  including empty descendants. A zero-height generated text block can consume
  a clamp line without moving real text ranges outside the apparent two-row
  area; it is now unknown. The sole narrow exception is the observed direct
  parent's empty `::before`, static block/right float with zero effective width,
  finite nonnegative height, zero margins/padding/borders, and no shape,
  transform or background-image layout. It does not grant a general pseudo-
  element exemption.
- Work remains explicitly bounded: 2048 descendant nodes, 2048 text-node range
  rectangles, 40000 UTF-16 text units, 64 ancestor levels and 2048 direct
  siblings; clamp-specific traversal additionally caps non-whitespace Unicode
  characters at 20000 and character rectangles at 40000. Exceeding a limit
  remains unknown rather than returning a truncated complete caption.
- The real `enrich_with_context` → readiness → snapshot → captured materializer
  regression includes the supported clamp layout and verifies exactly one
  navigation/materialization and owned-page-only closure. The 30-second shared
  readiness budget, cancellation, immediate identity/challenge checks, note
  rejection and downloader/probe guards were unchanged.

Implementer-attributed evidence, not an independent replay of the old code:
the six-case clamp matrix initially produced **2 failed / 4 passed**, and the
zero-height generated-prefix counterexample produced **1 failed in 1.53s**.
The final focused Douyin gate was **160 passed, zero skipped, 52.08s**. The
clamped/unclamped screenshot comparisons explicitly hold `display: flow-root`
constant: harmless empty-float painting is equal, while the generated-prefix
counterexample differs. These assertions also ran in the independent full
suite below. All DOM documents are synthetic and external requests are aborted;
the captured materializer is not a live media download or model invocation.

### Independent final verification

From `/tmp/longtian-media-validation.DeYMEC/third_party/MediaCrawler`:

```sh
../../backend/.venv/bin/ruff check --isolated --select E4,E7,E9,F,I media_platform/douyin/product_enrichment.py tests/test_product_media_douyin.py
../../backend/.venv/bin/ruff format --isolated --check media_platform/douyin/product_enrichment.py tests/test_product_media_douyin.py
TEST_CHROMIUM_EXECUTABLE=/home/jonathanhu237/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome PYTHONPATH=. .venv/bin/pytest -q tests/ --tb=short
```

- Maintained derivative suite: **1126 passed, zero skipped, 85.35s**. Only the
  inherited SQLAlchemy `MovedIn20Warning` remained.
- Scoped lint and format: **PASS**, both files. Local read-only scoped
  `git diff --check` also passed. No separate Python type-check command is
  configured for this derivative scope.
- Exact local SHA-256 values matched the remote files before the gate and
  remained unchanged locally after it:

| Derivative path | SHA-256 |
| --- | --- |
| `media_platform/douyin/product_enrichment.py` | `9d0a4ea33abf827dd8631d9df5f66855422dc491b538150b85b7780edd6cfa11` |
| `tests/test_product_media_douyin.py` | `873f29c5714ceab112b7363ef769f90a8098a0317262296137e300d54cbf73d5` |

The unchanged media helper remains
`08faedc72f1a24b9f978164ae578bb68389f12b0659608c716dbb3a2d72478c2` locally and
remotely. Both exact Douyin CDN hosts retain the same public-DNS/TLS/pinned
Host+SNI/redirect/file/size/MIME/audio guards. Backend and frontend were not
changed or rerun; their earlier **596 / 281** evidence remains historical.

No remaining blocking finding or spec discrepancy was identified in this
bounded patch. Unsupported/unknown CSS layouts and the four same-ID note
sources still remain incomplete. Universal layout support, actual model
quality, paid usage and successful real report generation are not established
by these tests. No runtime, media, database, profile or credential was copied;
the reviewer made no live browser/platform/API/model request and performed no
Git writes, deployment, commit, push or archive. Main owns the separately
authorized real-application acceptance and its result.
