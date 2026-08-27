# Visible Browser Search Adapter Guidelines

## Scenario: Low-frequency public search adapter

### 1. Scope / Trigger

Use this contract when adding a platform to the MediaCrawler derivative that discovers public links through a visible browser search page rather than a documented search API.

This contract applies to search-only adapters that register a new CLI platform, optionally reuse a project-account session, normalize visible result links, and persist a minimal discovery record. It does not authorize private API replay, signature reverse engineering, challenge automation, detail/comment crawling, or broad pagination.

### 2. Signatures

Platform registration is explicit:

```python
class PlatformEnum(str, Enum):
    PLATFORM = "platform"

class CrawlerFactory:
    CRAWLERS = {"platform": PlatformCrawler}
```

Browser boundaries:

```python
class PlatformCrawler(AbstractCrawler):
    async def start(self) -> None: ...
    async def search(self) -> None: ...

class PlatformWebClient:
    async def is_logged_in(self) -> bool: ...
    async def search(self, keyword: str, page_num: int = 0) -> list[dict]: ...
```

The minimum persisted discovery contract is:

```python
class SearchContent(BaseModel):
    content_id: str
    content_type: str
    title: str
    snippet: str = ""
    creator_hash: str = ""
    publisher_name: str = ""
    published_at_text: str = ""
    content_url: str
    source_keyword: str
    discovered_at: int
```

SQLite adds `add_ts` and `last_modify_ts` and upserts by `content_id`.

### 3. Contracts

#### Registration and modes

- Register the same stable platform key in the CLI enum, crawler factory, and platform config import.
- The first adapter supports `search` only. `detail`, `creator`, comments, media, and unsupported stores fail explicitly instead of returning an unexplained empty result.
- The default command shape is:

  ```bash
  python main.py --platform <platform> --type search --keywords <keyword> \
    --crawler_max_notes_count <hard-limit> --get_comment no --headless no \
    --save_data_option jsonl
  ```

#### Browser and authentication

- Launch a fresh, non-persistent, visible Chrome `BrowserContext`. Do not connect to an everyday browser, launch a persistent profile, or inject stealth scripts.
- `BrowserAuthStateStore` is the only cross-restart authentication persistence. Restore allowlisted Cookies before the first online login check and save them only after a successful online recheck.
- Use one Auth Page for the homepage, optional manual login, official safety challenges, and state saving.
- After authentication completes, create a never-navigated Search Page, close the Auth Page, and bind the search client to the Search Page. This prevents platform homepage routing from aborting the search redirect.
- An explicit manual-login loop may keep the visible page open while an official challenge is present. It may only poll the ordinary DOM login state and sleep. It must not reload, re-navigate, inspect challenge internals, or act on the challenge.
- A transient Playwright `Execution context was destroyed ... because of a navigation` error may be treated as an inconclusive manual-login poll. Other Playwright errors propagate.

#### Search and DOM

- Navigate exactly once per page through the platform's normal public search entry and accept the platform's normal redirect. Do not swallow `ERR_ABORTED`, retry navigation, or fall back to a private/internal endpoint.
- A recognized result, a recognized empty state, a safety challenge/block, and unknown structure are four distinct outcomes.
- Search challenges, mandatory login walls, HTTP 403/429, and unknown structure fail closed without retries.
- The shared Toutiao client may reread only a coherent pending DOM after its initial 1,500 ms wait:
  zero or one visible main container, empty candidates, and no explicit empty state. Allow at most
  20 additional 250 ms waits (21 snapshots total), with trusted-origin checks before and after every
  read. This is bounded page-readiness observation, not navigation/search retry or a wall-clock
  deadline. Malformed/ambiguous states, login/challenge and unsafe navigation stop immediately;
  pending-budget exhaustion is a structure error, never empty success. Cancellation propagates.
- Extract only visible candidate anchors plus a bounded nearby card container. Optional snippet/publisher/time extraction must prove that the selected container is at most 2,000 visible characters. Do not capture raw HTML or page-wide text as a result record.

#### URLs and data

- Decode visible redirect URLs offline with a fixed maximum depth, accept only HTTP(S), reject credentials and non-default ports, and require an explicit target-domain allowlist.
- Remove fragments and known tracking/search-session keys. Do not store redirect tokens or search IDs.
- Prefer a stable path content ID. If none exists, use a deterministic digest of the canonical URL.
- Apply publisher masking at the Pydantic persistence boundary, not only in a caller, so alternate call sites cannot persist a raw label.
- JSONL is append-only and must deduplicate within one run. SQLite must upsert by `content_id` across runs.
- Cookie names/values, QR payloads, LocalStorage, authentication headers, raw user IDs, avatars, profiles, IP locations, and raw page content never enter models, fixtures, logs, or task evidence.

#### Submodule delivery

- Commit and push the MediaCrawler derivative before updating the parent gitlink.
- The parent may move only to a reachable, clean submodule revision. Follow `../infra/submodule-guidelines.md`.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Empty keyword list or hard limit below one | Raise a configuration error before navigation |
| Headless, detail/creator, comments, or unsupported store selected | Fail explicitly; do not silently degrade |
| Auth state missing/invalid | Continue to online check and optional manual login |
| Auth state restored but online check fails | Enter manual login only when login is required |
| Manual login page is navigating | Treat only the canonical context-destroyed race as inconclusive; sleep and poll again |
| Official challenge during manual login | Keep the visible page open, log once, poll normally until success or timeout |
| Official challenge during search | Stop the platform run immediately |
| HTTP 403/429 or mandatory login wall during search | Stop without refresh, retry, or fallback |
| Results present | Normalize, allowlist, deduplicate, apply the hard limit, and store |
| Recognized empty state | Return an empty result list successfully |
| Coherent Toutiao pending DOM with neither result nor empty state | Reread within the fixed readiness budget; exhaustion raises a structure-change error |
| Malformed/ambiguous DOM or unsafe page origin | Raise a structure-change error immediately |
| Redirect exceeds maximum depth, target is external, scheme is invalid, or port is non-default | Reject the result without network follow-up |
| Cookie injection/save fails | Raise or warn without the underlying credential-bearing exception text; never save unverified state |
| SQLite record already exists | Update mutable fields and `last_modify_ts`; do not insert a duplicate |

### 5. Good / Base / Bad Cases

- **Good:** A fresh visible context restores allowlisted Cookies, confirms login online, closes the Auth Page, searches from a blank Search Page with one public navigation, stores bounded/minimized records, and exits cleanly.
- **Base:** No login is required. The adapter performs one first-page search, accepts zero or more allowlisted links, and writes no credential state.
- **Bad:** The adapter reuses an everyday/persistent profile, reads private responses, retries a challenge, captures the whole page, follows external redirects, trusts a Cookie file as proof of login, or logs credential-bearing exceptions.

### 6. Tests Required

1. Registration: CLI parsing and factory creation select the stable platform key; unsupported crawler modes fail.
2. Browser isolation: CDP and persistent-context launch paths are never selected; Auth and Search Pages are distinct; Auth Page closes before search.
3. Authentication order: restore → online check → optional manual login → online recheck → save only after success.
4. Manual navigation race: only the canonical context-destroyed error continues polling; unrelated errors propagate.
5. Manual challenge: repeated challenge polls log once, allow later success, and time out without saving or searching.
6. Search navigation: one public `goto()` only; aborts and blocks propagate with no retry/fallback/evaluation.
7. DOM fixtures: normal result, missing optional fields, bounded ancestor, recognized empty page, mandatory login, challenge, and structure drift.
   For Toutiao, include real offline delayed-render fixtures (with explicit UTF-8 encoding), exact
   21-read/20-additional-wait exhaustion, early success, immediate safety/malformed stops,
   pre/post-read origin checks and cancellation with owned-page-only cleanup. Browser fixtures must
   actually run with a detected executable or the validated test-only `TEST_CHROMIUM_EXECUTABLE`.
8. URL table: one/two redirect layers, excess nesting, current/legacy paths, external host, credentials, invalid scheme, default/non-default ports, fragments, and tracking keys.
9. Privacy: model construction masks publisher labels and contains no forbidden identity or authentication fields.
10. Store: JSONL contract/in-run deduplication and isolated SQLite insert/update idempotency.
11. Real regression: one keyword, one page, hard limit, visible browser; then one manual login and a full browser restart that restores and confirms the session without another prompt.
12. Cleanup: task-created authentication state and temporary profiles/directories are removed after evidence is recorded; existing runtime data is untouched.

### 7. Wrong vs Correct

#### Wrong

```python
# Reuses the homepage tab, retries a redirect, and trusts stored state.
page = await persistent_context.new_page()
await auth_state.restore(context)
await page.goto(home_url)
try:
    await page.goto(private_search_url)
except PlaywrightError:
    await page.reload()
authenticated = True
```

#### Correct

```python
context = await browser.new_context()
await auth_state.restore(context)

auth_page = await context.new_page()
await auth_page.goto(home_url)
authenticated = await client(auth_page).is_logged_in()
if require_login and not authenticated:
    await manual_login(auth_page)
    authenticated = await client(auth_page).is_logged_in()
if authenticated:
    await auth_state.save(context)

search_page = await context.new_page()  # never navigated before search
await auth_page.close()
results = await client(search_page).search(keyword, page_num=0)  # one goto
```
