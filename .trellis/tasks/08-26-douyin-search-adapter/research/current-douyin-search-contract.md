# Current Douyin search contract

## Audited reusable capability

- `media_platform/douyin/core.py:214-268` performs sequential keyword search and calls
  `search_info_by_keyword`, but then writes the generic store, fetches media, fetches comments,
  sleeps, and logs keywords and result IDs. The product path must not call this method.
- `media_platform/douyin/client.py:169-209` uses the official web general-search endpoint
  `/aweme/v1/web/general/search/single/`, fixed general channel, count 15, offset and the preceding
  response's search ID. The endpoint is explicitly excluded from the current `a_bogus` branch at
  lines 114-121.
- `media_platform/douyin/client.py:71-135` is not a safe product boundary: it reads the entire page
  LocalStorage, owns proxy-refresh behavior, and includes raw response text in raised errors.
  Product search needs a separate single-attempt client that reads only the one required temporary
  value and sanitizes every failure.
- `media_platform/douyin/auth.py:28-110` already provides a network-backed secret-free account
  result. It keeps account identity and the raw account response inside the task page. Search should
  reuse this authority and separately recognize visible challenge evidence.
- `store/douyin/__init__.py:158-183` confirms the reusable public work projection: `aweme_id`,
  `desc`, `create_time`, `author.uid`, `author.nickname`, and the canonical
  `https://www.douyin.com/video/<aweme_id>` link. Counters, covers, download URLs and source-keyword
  logging are outside the product contract.

## Product boundary

- Reuse one borrowed default context and one registered task-owned Douyin page.
- Visit only `https://www.douyin.com`, run the authoritative online account probe, refresh only
  Douyin cookies, read only the search-required `xmst` value, and send bounded sequential requests.
- Use no proxy, retry, generic client, generic crawler store, details, comments, creator pages,
  counters or media helpers.
- Treat the platform's default general ordering as unstable. Cross-run identity is the numeric
  `aweme_id`; only exact `https://www.douyin.com/video/<same-id>` links may leave the worker.
- Stop and return to planning if the live endpoint now requires context-wide mutation, repeated
  anti-bot retries, automated slider work, raw credential export or broader data extraction.
