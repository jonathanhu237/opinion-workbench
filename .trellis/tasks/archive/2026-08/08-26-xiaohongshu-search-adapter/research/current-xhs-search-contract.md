# Current Xiaohongshu Search Contract

## Repository evidence

- `media_platform/xhs/client.py:330-358` calls the domestic official endpoint
  `/api/sns/web/v1/search/notes` with `keyword`, one-based `page`, fixed `page_size`, one
  per-term `search_id`, default `general` sort and note type `ALL`.
- `media_platform/xhs/core.py:280-353` shows why the generic crawler is not a product boundary: it
  logs keywords and raw search responses, fetches every note detail, stores results, downloads media,
  fetches comments, sleeps and relies on the generic retrying client.
- Historical source commit `e82dcae` confirms a search result item exposes stable `id` and
  `note_card.display_title` before any detail request. The product adapter can therefore provide a
  useful title and link without fetching note details.
- `media_platform/xhs/playwright_sign.py` delegates signing to the existing `xhshow>=0.2.0`
  dependency. It needs the URI, exact compact payload and scoped Cookie string; it does not require
  LocalStorage or a context-wide browser script.
- `media_platform/xhs/client.py:124-198` is unsuitable for product search because `request()` is
  decorated for three attempts, can refresh proxies, and logs challenge metadata/raw responses.
- `media_platform/xhs/core.py:214-276` and `client.py:273-307` already provide the authoritative
  online login proof through `/api/sns/web/v1/user/selfinfo` in the approved borrowed Chrome
  context.
- `store/xhs/__init__.py:86-132` demonstrates the generic store persists `xsec_token` and includes it
  in note URLs. The product boundary must not call this store or emit that token.
- `config/xhs_config.py:26-35` and `help.py:300-318` show that detail/API workflows expect
  `xsec_token`; product search deliberately does not use those detail workflows.
- Past session `01a00d6e-ba73-7a13-a6ba-b5512b4f85f2` recorded that direct XHS search-page
  navigation repeatedly timed out while the discovery/home page remained usable. Product search
  should use the stable official home page for ownership/auth and the bounded search API for data.
- A 2026-08-26 sanitized live diagnosis observed one successful first page with 14 safe note cards,
  2 recognized auxiliary cards, and 6 otherwise-valid note cards whose `display_title` normalized
  empty. No raw response, keyword, signature, token, or author identity was retained.
- After releasing a competing Chrome automation client, 2026-08-26 live product runs completed all
  five terms. The first completed run stored 12 results; the immediate rerun stored 14 results with
  8 overlapping identities correctly classified as repeated. Overlap kept `first_seen_at` stable,
  advanced `last_seen_at`, and every stored URL was query-free and correlated with its note ID.
- The mandatory query-free-link gate then failed: opening one stored canonical `/explore/<note_id>`
  URL in the same logged-in Chrome session redirected to Xiaohongshu's unavailable-note page with
  business error 300031. This proves that a stable note ID alone does not guarantee a web-openable
  original link. No xsec value was persisted or exposed during the test.
- A subsequent sanitized live diagnosis passed authoritative login and observed one successful
  first-page response with 20 structurally valid cards. The exact target appeared once with a
  bounded nonempty `xsec_token`, while the response omitted `xsec_source`; no raw response, term,
  token or author identity was retained.
- Existing MediaCrawler search-origin behavior supplies the missing operation context internally:
  `store/xhs` hardcodes `pc_search`, and the XHS client defaults an empty source to `pc_search`.
  Product opening therefore derives this fixed channel from the trusted search operation rather
  than treating a response field as input.
- The corrected 2026-08-26 live gate returned the fixed `opened` outcome for one stored run/result
  relation. After FastAPI shutdown released the CDP transport, the handed-off Chrome tab remained
  open on the exact official explore path; its canonical and Open Graph URLs matched that path, a
  visible note container/title/media had rendered, and no unavailable or challenge marker was
  present. SQLite schema/content/term scans and the API response contained no xsec value. No URL,
  term, token, author identity or raw page content was retained as task evidence.

## Product-safe boundary

1. Create and register one task-owned page in the already approved default Chrome context.
2. Visit only `https://www.xiaohongshu.com` and run the existing authoritative account proof.
3. Read cookies only for the domestic Xiaohongshu origin; do not read LocalStorage.
4. Generate one search ID per term and sign the exact compact search payload with the existing
   `xhshow` helper.
5. Send at most `ceil(max_results_per_term / 20)` single-attempt POST requests per term to the
   allowlisted `edith.xiaohongshu.com` origin; no proxy, retry or alternate browser.
6. Accept only recognized note-card items with a stable lowercase 24-hex note ID and usable bounded
   `display_title`. Ignore a recognized `normal`/`video` note only when that ID and `note_card` are
   otherwise valid and its title is absent, null or a blank string; never synthesize a title. Known
   `rec_query`/`hot_query` auxiliary items are not content.
7. Normalize only title, note type and masked publisher information present in the search card.
   Ignore covers, counters, xsec values and other metadata; do not fetch detail or media.
8. Construct `https://www.xiaohongshu.com/explore/<note_id>` from the ID as query-free identity
   metadata. The 2026-08-26 live gate proved this cannot be treated as a reliable direct link.
9. Under the user-approved replacement contract, opening a stored result rereads its first matched
   term from SQLite, performs one first-page search, finds the exact ID, and validates that card's
   bounded nonempty token. The token does not cross the worker boundary or persist; no alternate
   term, page, retry or detail request is permitted.
10. The implemented open boundary derives the fixed search channel `pc_search` from one private
    worker-owned constant and never reads or trusts a response-provided source. The bounded token,
    derived channel and official destination remain inside the worker, which returns only a fixed
    outcome. The product repository proves run/result ownership and original matched-term order
    without a schema change; the React caller sends an exact no-body request.

## Terminal evidence

- HTTP 401 or a recognized login response: `login_required`.
- HTTP 461/471 or recognized captcha/verification response: `manual_challenge_required`.
- HTTP 403/429, business code 300011/300012 or recognized block text:
  `platform_blocked_or_rate_limited`.
- Successful exact empty `items`, or only valid untitled/auxiliary cards, with coherent
  `has_more=false`: `completed_empty` when every term emits no safe content.
- Unknown success shape, contradictory pagination, unknown model/type, missing or invalid ID,
  missing note card, non-null non-string title shape, or other malformed non-empty card:
  `structure_changed`.
- Transport/runtime failure without platform evidence: `internal_error`.

## Stop conditions

- Do not implement automated CAPTCHA/slider/SMS handling, signature fallbacks, retry loops, proxies,
  broader browser-state extraction or detail requests.
- If live opening requires xsec persistence/exposure, context-wide mutation, repeated pages/terms or
  a different private endpoint, stop and return to planning.
- The user approved the explicit in-memory on-demand-open design after the 300031 live result. Do not
  weaken it into a token-bearing API/link/database field or silently add fallback searches.
