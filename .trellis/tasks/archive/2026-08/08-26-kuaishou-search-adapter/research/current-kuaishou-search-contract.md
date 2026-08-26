# Current Kuaishou Search Contract

## Confirmed source behavior

- `media_platform/kuaishou/core.py:75-80` fixes the official origin and cookie scope to
  `https://www.kuaishou.com`.
- `core.py:116-121` creates a page, registers it when CDP is active, installs
  `KS_SIGN_CAPTURE_SCRIPT` on that page, and navigates to the official origin.
- `core.py:189-242` proves the existing injected authentication flow keeps the signer page-local,
  uses an authoritative online probe, and closes only registered task pages.
- `core.py:244-302` shows the generic search path is unsuitable for the product boundary: it logs
  keywords, forces a 20-result page, writes generic stores, sleeps, and fetches comments.
- `media_platform/kuaishou/client.py:117-159` shows the shared signed request retries rate limits
  three times and places the full result inside raised exceptions. Product search must not call it.
- `client.py:172-189` establishes the current official search request shape:
  `/rest/v/search/feed` with `keyword`, numeric-string `pcursor`, `page="search"`, and propagated
  `searchSessionId`.
- `media_platform/kuaishou/help.py:29-86` establishes that signing is generated from the official
  page's own runtime through a page-local capture script; no separate signing library is present.
- `store/kuaishou/__init__.py:55-79` identifies the bounded normalization candidates: `photo.id`,
  `caption`, `timestamp`, author ID/name, and canonical `/short-video/<id>` URL.
- `frontend/src/assets/platforms/kuaishou.svg` is the already reviewed product logo asset.

## Product boundary derived from evidence

- Reuse the existing page-local capture script and signing helper on one task-owned page.
- Implement a product-specific, single-attempt signed request instead of changing the generic
  three-retry client used by standalone MediaCrawler flows.
- Refresh only Kuaishou cookies and require the existing authoritative online login proof before
  searching.
- Request no more than the product hard limit, normalize only stable works, and emit strict worker
  events; FastAPI remains the sole product store and deduplication owner.
- Never call comments, details, profiles, media helpers, proxy pools, or generic stores.
- Treat HTTP 403/429 or recognized `result=2` as platform restriction/rate limit. Treat an unknown
  success/error shape or unusable signer as protocol/structure drift, not an empty result.

## Open technical validation

- Fixture tests must pin the exact successful response shape, empty shape, login/challenge evidence,
  rate-limit code, and pagination/session behavior.
- Real-browser acceptance must prove the current signed endpoint still works with the borrowed
  Chrome session and that the second identical run is deduplicated without another CDP connection.
