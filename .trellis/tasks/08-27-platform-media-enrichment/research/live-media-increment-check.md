# Live-media increment check — interim, 2026-08-28

Status: **PASS for this scoped increment; child remains in progress.** This is not
final child acceptance. Main extended this interim pass to the separately frozen
DY/TT adapters, paired legacy-source validators and exact hosts. All reviewed fixes
are frozen and covered by the reported final maintained-suite gate.

## Scope and method

Loaded `check.jsonl`, its referenced contracts/specifications, child PRD/design/
implementation plan and `research/live-dom-observations.md`. Applied the
`trellis-check` review and `trellis-before-dev` change-boundary guidance. Reviewed
the frozen WB/KS/XHS `product_enrichment.py` files, their three dedicated test files,
and the task-only `verification/live_asset_probe.py`. After explicit scope extension,
also reviewed the frozen DY/TT adapters and dedicated tests, the TT URL corpus and
both validators, the three-entry exact CDN host increment, and the new media-fidelity
specification plus its guide/index pointers.

The reviewer performed source inspection and local scoped edits only. No real
browser/platform/provider, user database/runtime/credentials, Git operation or local
test execution occurred. Main owns source synchronization and Centaurus validation.
Shared protocol/I/O/backend and DY/TT source were not modified by this review.

## Findings (fixed)

### L1 — XHS page projection could convert malformed media into complete inventory

File: `third_party/MediaCrawler/media_platform/xhs/product_enrichment.py`.

The JavaScript snapshot converted present non-object `video` values to `null`.
A normal note with complete text and an empty image list then passed the Python
projection's `video is None` test and became ready text-only. Separately, every
H264 entry was wrapped in a dictionary, including malformed null/string/array
entries. This erased the existing `all(isinstance(item, dict))` inventory check;
a valid stream followed by a malformed entry could likewise become ready after
a successful probe. The pure projection's unknown-inventory handling was correct;
the lossy preceding JavaScript transformation bypassed it.

Main ran the tests-only snapshot against the unchanged adapter on Centaurus:
**7 failed, 36 deselected, zero skips in4.41s**, all because `ready` was returned
where `partial` was expected. The regression executes the actual script in an
offline Chromium page with every route aborted, then uses the real projection/
materialization with fake media I/O.

Fix: only missing/null video becomes null; other malformed values become a bounded
empty-object unknown marker. Malformed H264 entries remain null, preserving the
existing Python check. No raw malformed values, new wire field, fallback or shared
validator change was introduced. Existing normal/absent/valid-media cases remain.

Regression: `tests/test_product_media_xhs.py::test_javascript_preserves_unknown_inventory_for_malformed_media`
covers four malformed video shapes and three malformed later stream entries.
The existing camel/snake real-JavaScript test also now asserts complete inventory
and the exact URL for a valid video, then replaces the note with a proven ordinary
absent-video note and requires JS-to-materialization text-only ready. This prevents
an indiscriminate all-unknown workaround from satisfying only the negative tests.

### L2 — Task probe skipped descriptor cleanup if downloader close failed

File: `verification/live_asset_probe.py`.

The cleanup block awaited downloader closure before calling `staging.close`.
An exception or cancellation from the first action skipped the second. The outer
temporary-directory context still removed its private directory, but that did not
explicitly close the staging directory descriptors. A separate input-shape issue
let list/dict `kind` values raise during set membership instead of returning the
intended `invalid_input` outcome. These were source-traced findings, not claimed
as a remotely reproduced red gate.

Fix: nested `try/finally` always runs staging cleanup, and a strict string check
precedes kind membership. The16KiB input cap,6MiB download cap, private stdin locator,
sanitized exception output and exact production downloader/probe are unchanged.

New `verification/test_live_asset_probe.py` uses fake downloader/probe classes and
real isolated temporary staging. It checks both held descriptors and root cleanup
after close failure/cancellation, one download on success, metadata-only output,
sanitized main errors, malformed kinds before resources and oversized stdin.
It makes no network or ffprobe subprocess call.

## Findings (not fixed) and acceptance limits

No additional concrete defect was found in the reviewed WB/KS or frozen DY/TT
increments and their tests.

- WB keeps media inventory unknown even when exact-ID text and picture candidates
  are available. Missing/long/clipped text is not silently completed; avatars,
  unrelated objects and cover/video guesses are excluded. The single owned page
  is checked before/after projection; tests cover redirect/cancel/user-tab safety.
- KS uses one minimized exact-ID GraphQL request with origin-scoped cookies and
  fixed origin/path. It does not claim unverified `status==1` success. Caption and
  inventory remain incomplete even if one progressive video probes successfully;
  covers, manifest-only transport and missing audio stay explicit. A failed chosen
  stream does not trigger another variant, cover, search or profile fallback.
- XHS keeps the approved one-first-page/first-stored-term lookup, exact note ID,
  fixed token source and owned-page lifecycle. Its bounded per-note content-only
  projection is the approved source seam, not a whole hidden-state/storage export.
  Tokens, user objects and signed locators are not returned in normalized results.
- DY selects one matching information region and player for the stored numeric ID,
  with one canonical navigation and a bounded structural wait. Missing/ambiguous
  scope, visible expansion, clipping/unknown geometry and absent actual currentSrc
  cannot become complete input. Empty caption is allowed only with actual media.
  It has no cookie/storage/search/API fallback, and offline fixtures make forbidden
  hidden-state/storage getters throw. Independent file/audio probing remains required.
- TT selects the unique observed article/title and its exact same-root end control.
  Body extraction excludes metadata/player UI/hidden content; missing end, expansion,
  clipping, lazy images and unknown embedded/CSS/pseudo-element media remain incomplete.
  Only actual data-src/currentSrc candidates are selected; posters/placeholders are
  not replacements. Unknown layouts receive no page-wide-text or endpoint fallback.
- Paired source validators and22 TT URL cases admit only the exact historical
  `http://www.toutiao.com/a<same-numeric-id>` form, with an optional trailing slash.
  Port/userinfo/query/fragment/extra path/other HTTP host or route fail closed.
  The adapter upgrades to HTTPS before its sole navigation, accepts only the final
  same-ID WWW article route, and preserves the original stored URL in its result.
- The new host entries are exact `v26-weba.douyinvod.com`, `p3-sign.toutiaoimg.com`
  and `v3-web.toutiaovod.com`, matching the main's bounded source observations.
  There is no wildcard/suffix relaxation; WB/KS/XHS production allowlists remain
  empty. A host entry is not itself proof of a valid asset or complete source.
- Remaining WB video/complete inventory, KS status/image-post inventory and real
  XHS token-assisted media acquisition are unfinished acceptance dependencies.
  The direct XHS300031 observation is not a platform-wide or deletion conclusion.
- The earlier abnormal-worker-death/read-only-probe reclamation limitation remains
  as recorded in `enrichment-implementation-check.md`; it is not reclassified as
  whole-process-group cleanup proof here.

The main's DY372 MP4 and TT143 single-image file checks in the observation record
prove those actual file downloads/probes and their task-owned temporary cleanup.
They do not prove complete-source extraction, worker/backend handoff, live product
cancellation/sentinels or five-platform support. The recorded disappearance of a
baseline browser tab also precludes claiming that the research visit passed a live
all-user-tabs-preserved gate. No further live operation is requested by this review.

## Verification

- Main-run XHS red:7 failed as described above.
- Main-run patched WB/KS/XHS plus task-probe gate: **110 passed, zero skips in5.70s**.
  The later positive-only XHS assertions do not change product code and are included
  in the final explicit maintained-suite result below.
- Final main-run fork: **1035 passed, zero skips in36.97s**, with one inherited
  SQLAlchemy warning, using `PYTHONPATH=.` and the configured offline Chromium:
  `.venv/bin/pytest -q tests/ --tb=short`.
- Final main-run task-probe suite, separate from `tests/`: **10 passed in0.12s**.
- Final main-run backend: **462 passed in9.20s**; backend Ruff/format checks passed
  for58 files. No backend change was made by this review.
- Lint/format: main's20-file scoped gate passed,18 fork files plus2 task helpers,
  using isolated Ruff `E4,E7,E9,F,I` and isolated format checks. This is not a claim
  that all legacy fork Ruff rules are clean. Main only reformatted one task-probe
  test function signature onto one line; no semantic change. The local
  reviewer had no `ruff` executable and did not run it.
- TypeCheck: no separate checker run reported or claimed for this increment.
- Historical fork867/backend462 gates establish the earlier shared foundation,
  **not** verification of this increment or current final source.
- Source review found no required contract/spec change: the fixes restore existing
  unknown-inventory and owned-cleanup semantics without expanding interfaces. Main's
  new `backend/media-projection-guidelines.md` and linked thinking guide correctly
  capture the XHS rule without claiming complete platform or live acceptance.
- Main reported the frozen DY focused checkpoint:69 passed, zero skips in3.27s.
  The sole prior failure was a synthetic missing-heading fixture collapsing its
  region to zero height; only that fixture was corrected, not the production guard.
- The main's TT/protocol/projection166-test checkpoint preceded the final two
  pseudo-element cases; it is superseded by the final explicit maintained-suite gate.
- Main accidentally ran default pytest discovery, reaching the legacy `test/`
  Redis/Mongo integrations:6 Redis authentication failures,8 Mongo skips and1044
  passing cases. This is a failed broader invocation, **not** a green maintained
  product gate. No service/configuration change is authorized to make it pass;
  the final maintained-suite command explicitly targets `tests/`.

The focused command from the derivative root used the existing isolated
environment and configured offline Chromium:

```sh
pytest -q tests/test_product_media_weibo.py tests/test_product_media_kuaishou.py tests/test_product_media_xhs.py ../../.trellis/tasks/08-27-platform-media-enrichment/verification/test_live_asset_probe.py
```

All execution results above are main-run evidence; the reviewer did not replay
tests or live calls locally. Main additionally reported closing its owned audit tab
and discarding temporary media locators from Node memory; temporary media files had
already been removed. This does not resolve the separately unproven baseline-tab
observation or substitute for product live cancellation/ownership acceptance.

Reviewer edits are limited to the XHS adapter/test, task probe/new fake test, and
this report. No further source or contract change is required by this scoped pass.
