# Combined pre-commit gate — 2026-08-28

**PASS.** The existing independent `trellis-check` reviewer reran the applicable
complete gates for the frozen Douyin media repair and report-source hyperlinks.
No product change or new blocking finding was needed. This report is the only
local file written by this review; main owns staging, both commits/pushes, the
parent gitlink and fresh-clone reproducibility checks. This gate does not claim
that publication or archive has occurred.

## Frozen snapshot

Read the current check manifest, referenced contracts, PRD/design/implement and
the prior `douyin-media-repair-check.md` and `report-source-links-check.md`.
Their detailed code-review conclusions remain applicable: all five source
hashes below are unchanged. Main's later summary-6 evidence supersedes the
historical live-pending status in the earlier caption review, not its code gate.

Only the five explicit source/test paths below were synchronized one-way from
local source to `Centaurus:/tmp/longtian-media-validation.DeYMEC/` using
`rsync -a --relative`. Local and remote SHA-256 values matched before and after
testing. A separate read-only checksum dry-run also found no content differences
in backend `src`/`tests`/manifest/lock and frontend `src`/manifest/lock/TS/Vite/
Vitest configuration. No runtime, database, credentials, browser profile, media,
dependency directory or Git metadata was transferred.

| Repository-relative file | SHA-256 |
| --- | --- |
| `third_party/MediaCrawler/media_platform/douyin/product_enrichment.py` | `9d0a4ea33abf827dd8631d9df5f66855422dc491b538150b85b7780edd6cfa11` |
| `third_party/MediaCrawler/tests/test_product_media_douyin.py` | `873f29c5714ceab112b7363ef769f90a8098a0317262296137e300d54cbf73d5` |
| `third_party/MediaCrawler/tools/product_media.py` | `08faedc72f1a24b9f978164ae578bb68389f12b0659608c716dbb3a2d72478c2` |
| `frontend/src/routes/collection-ai-summary.tsx` | `15723b9cad829df28d1ed7e274badb33ab0cd97c7f2f604f3de8d33ed95203d5` |
| `frontend/src/routes/collection-ai-summary.test.tsx` | `9064a70435764d9780cc7047a5ffd00074bbb2bac32f1d9c34378e80453c5977` |

## Independent commands and results

The three gate processes ran independently in parallel against that same
verified isolated snapshot. No source synchronization occurred while tests ran.

From `/tmp/longtian-media-validation.DeYMEC/third_party/MediaCrawler`:

```sh
../../backend/.venv/bin/ruff check --isolated --select E4,E7,E9,F,I media_platform/douyin/product_enrichment.py tools/product_media.py tests/test_product_media_douyin.py
../../backend/.venv/bin/ruff format --isolated --check media_platform/douyin/product_enrichment.py tools/product_media.py tests/test_product_media_douyin.py
TEST_CHROMIUM_EXECUTABLE=/home/jonathanhu237/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome PYTHONPATH=. .venv/bin/pytest -q tests/ --tb=short
```

- Maintained `tests/`: **1126 passed, zero skipped, 87.30s**. Only the inherited
  SQLAlchemy `MovedIn20Warning` remained. Legacy root `test/` external-service
  modules were not selected.
- Scoped Ruff and format: **PASS**, all three changed derivative files.

From `/tmp/longtian-media-validation.DeYMEC/backend`:

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
PYTHONPATH=src .venv/bin/pytest -q tests/ --tb=short
```

- Backend integration suite: **596 passed, zero skipped, 14.05s**.
- Ruff and format: **PASS**, 69 formatted files. There is no separate configured
  Python type-check gate for this scope.

From `/tmp/longtian-media-validation.DeYMEC/frontend`, using mise Node
**24.20.0** and pnpm **11.14.0**:

```sh
mise x node@24 pnpm@11.14.0 -- pnpm install --frozen-lockfile
mise x node@24 pnpm@11.14.0 -- pnpm format:check
mise x node@24 pnpm@11.14.0 -- pnpm lint
mise x node@24 pnpm@11.14.0 -- pnpm typecheck
mise x node@24 pnpm@11.14.0 -- pnpm test:run
mise x node@24 pnpm@11.14.0 -- pnpm build
```

- Frozen install, Prettier, TypeScript and production build: **PASS**.
- Oxlint: **PASS**, 70 files, zero warnings/errors.
- Vitest: **288 passed / 14 files / zero skipped, 8.48s**, including all 26
  summary component cases. Existing isolated dependencies were not a symlink;
  no shared dependency target was replaced or deleted.

## Coverage and delivery limits

These are source-only automated gates: real Chromium executes synthetic,
network-disabled DOM fixtures, while provider/browser/HTTP boundaries use the
existing fakes. The reviewer did not operate user Chrome, call a real platform
or model, inspect credentials, touch the user database or change running services.

Main's separately recorded real **summary 6** covered the same five saved
Douyin run-41 sources: **one complete actual video with its caption and audio**
reached one item analysis and one text-only composition; **four unsupported
same-ID note redirects remained input-incomplete with no model calls**. Its
2 requests / 13,518 tokens are prior live evidence, not calls made by these
tests. This is not image-post support, five-platform acceptance, an independent
audio-accuracy benchmark or a batch-wide report. Cross-generation paid cache
reuse was not live-tested; UUID replay and automated reuse are distinct evidence.

The hyperlink smoke remains main-attributed: saved summary 6, correct source
href, inline underline/focus and no overflow at the observed 380px report width.
No live XHS opening or full live Tab-order claim is added. Fork-first publication,
reachable parent gitlink and fresh-clone checks are separately main-owned
delivery evidence under the user's commit/push authorization, outside this
source-only gate. The reviewer performed no Git writes,
commit, push, deployment or archive.
