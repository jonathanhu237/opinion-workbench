# Current Weibo Search Contract

## Purpose

Record the repository evidence that constrains the first product-level Weibo search adapter. This
is an internal code audit; it does not claim that the private mobile endpoint is stable or publicly
supported.

## Existing MediaCrawler behavior

- `media_platform/weibo/core.py` maps four search modes to `SearchType` and calls
  `WeiboClient.get_note_by_keyword()` for every page. The generic crawler reads comma-separated
  global keywords, forces a ten-item page size, can request more pages, and then enters optional
  full-text, image, and comment flows.
- `media_platform/weibo/field.py` identifies `REAL_TIME` as search type value `61`; the product has
  chosen this fixed mode for the first release.
- `media_platform/weibo/client.py` calls `GET https://m.weibo.cn/api/container/getIndex` with a
  `100103type=<type>&q=<term>` container ID. Its shared request method retries up to five times and
  logs raw response text or decoded error data before raising `DataFetchError`.
- `media_platform/weibo/help.py` treats card type `9`, including nested card groups, as content
  results. It does not provide a product-normalized model or explicit empty/login/challenge/error
  outcome.
- `store/weibo/__init__.py` already demonstrates the useful narrow fields: mblog ID, HTML-stripped
  content, platform creation time, canonical `https://m.weibo.cn/detail/<id>` link, anonymous
  creator hash, masked nickname, and source keyword. The product worker must emit these fields
  directly and must not invoke MediaCrawler stores.

## Existing product boundaries

- The persistent worker currently accepts product search only for platform `toutiao` and dispatches
  only `search_toutiao_with_context()`.
- The strict worker item shape is already platform-neutral enough for Weibo: content ID/type,
  title, snippet, masked publisher identity, display publication time, canonical URL, and discovery
  timestamp. Platform validation and URL allowlists are currently Toutiao-only.
- FastAPI request/response models, worker validation, repository SQL, and SQLite version 2 constrain
  the platform to `toutiao`. Adding `wb` requires a version 3 migration that rebuilds both parent
  tables and their dependent relationship tables while preserving existing Toutiao data.
- The React collection start form shows a fixed Toutiao target. History/detail and API runtime
  decoders also assume one platform.

## Planned safety boundary

- Reuse the existing persistent borrowed-Chrome worker and current default browser context.
- Use a task-owned official Weibo page only to establish official origin and refresh allowlisted
  Weibo cookies into a product-specific client. Never inspect or mutate a pre-existing tab.
- Execute the internal search endpoint sequentially with fixed real-time mode and a hard per-term
  result limit. Do not use the generic crawler loop, global config, stores, full-text, comments,
  media, proxies, or fallback browser.
- Product search performs one HTTP attempt per requested page. HTTP 403/429 and recognized platform
  rejection stop immediately; no generic five-attempt retry applies.
- Decode only the bounded fields required by the strict search item. Unknown/malformed response
  shapes fail closed. Raw response data, platform messages, terms, Cookies, and exceptions never
  enter stdout events, product logs, API errors, or acceptance evidence.
- Authentication status is not assumed from historical UI state. Return `login_required` only for a
  recognized current response or official page state that requires login; otherwise classify the
  actual response as empty, blocked/challenged, structure changed, or internal failure.

## Validation implications

- Add focused fixtures for flat and nested result cards, duplicates, HTML stripping, missing IDs,
  bounded text, exact real-time request parameters, limits across pages, and each terminal outcome.
- Extend both sides of the strict search protocol with platform-dependent URL and item validation.
- Prove migration 2→3 preserves Toutiao runs/results and accepts new `wb` rows without cross-platform
  deduplication.
- Run one real borrowed-Chrome Weibo keyword search plus a repeated run while a pre-existing sentinel
  tab remains unchanged. Record categories and counts only; retain no raw platform response.
