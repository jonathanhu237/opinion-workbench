# 实施计划

## Phase A: Platform Skeleton and Pure Contracts

- [x] Confirm the MediaCrawler submodule is clean at the parent-pinned revision and inspect current CLI/factory/store/test patterns before editing.
- [x] Add `toutiao` to the crawler factory, CLI enum/help and base/platform config without changing MediaCrawler API/Web UI enums.
- [x] Add the minimal Pydantic result model, typed exceptions and pure URL/result normalization helpers.
- [x] Add table-driven offline tests for URL unwrapping, host allowlisting, content ID/type classification, optional fields, duplicates, challenges, empty results and structure drift.

## Phase B: Visible-Browser Search Adapter

- [x] Implement `ToutiaoWebClient` over Playwright `Page` normal navigation and visible DOM only; do not add response listeners, private endpoint calls, stealth scripts or request signing.
- [x] Enter search through `www.toutiao.com/search/?keyword=...`, consume the normally redirected result DOM, and propagate navigation errors without retry or direct `so.toutiao.com` fallback.
- [x] Run homepage authentication and search on distinct Pages in one temporary context; create the blank search Page only after auth/save, close the auth Page, and perform exactly one search navigation.
- [x] Implement `ToutiaoCrawler` with search-only enforcement, visible-browser enforcement, per-keyword first-page navigation, serial hard limits, fixed delay and fail-closed stop conditions.
- [x] Force a fresh standard Chrome `BrowserContext` on every run; ignore CDP/persistent-profile settings so `BrowserAuthStateStore` is the only cross-restart authentication state.
- [x] Implement in-run deduplication and source-keyword propagation; keep detail, creator, comments and media paths unavailable.
- [x] Add orchestration tests proving one page per keyword, correct ordering/limits, challenge propagation and absence of private-network behavior.

## Phase C: Optional Project-Account Login

- [x] Implement a DOM-based live login check and visible manual login wrapper without automating QR/SMS/safety challenges.
- [x] Restore `BrowserAuthStateStore(platform="toutiao")` before the first live check and save only after a successful post-login live check; `TOUTIAO_REQUIRE_LOGIN=False` must preserve anonymous search.
- [x] Add authentication tests for anonymous mode, existing valid login, interactive fallback, failed post-login check, timeout/challenge, disabled persistence and credential-safe logging.

## Phase D: JSONL and SQLite

- [x] Add `store/toutiao` with JSONL and SQLite implementations only; unsupported save options fail clearly.
- [x] Add additive `ToutiaoContent` ORM model and SQLite upsert by `content_id`.
- [x] Extend privacy regression coverage so raw account identifiers and unmasked publisher labels cannot enter the model/store.
- [x] Test JSONL field shape and SQLite insert/update idempotency with isolated temporary paths/databases.

## Phase E: Verification and Real Regression

- [x] Run targeted Toutiao tests.
- [x] Run the complete dependency-free MediaCrawler `tests/` suite.
- [x] Run `python -m compileall` for changed Python packages and scoped pre-commit for every changed/new file; repository-wide pre-commit remains affected by unrelated baseline drift documented in offline validation.
- [x] Run secret and forbidden-field scans; verify no raw HTML, real Cookie values, QR data, persisted search token or authentication header is present in code, fixtures, logs or Trellis evidence.
- [x] Run one visible, single-page `龙田街道` search in the fresh non-persistent standard Chrome context with maximum ten results; verify no CDP port/profile directory is created and record only non-sensitive counts and field/host validity.
- [x] With user interaction, complete one project-account login and verify a full browser restart reuses a server/DOM-confirmed session; an official login challenge may be completed manually within the configured wait, but timeout must stop without saving.
- [x] After confirming no TCP `9222` listener remained, permanently remove all six explicit task-created `/tmp` validation directories, including the temporary `0600` auth-state file, without touching existing project runtime directories.

## Validation Commands

Run from `third_party/MediaCrawler` using the repository's configured Python environment:

```bash
pytest -q tests/test_toutiao_url.py tests/test_toutiao_parser.py tests/test_toutiao_crawler.py tests/test_toutiao_auth_state.py tests/test_toutiao_store.py
pytest -q tests
python -m compileall main.py cmd_arg config media_platform/toutiao model/m_toutiao.py store/toutiao database tests
pre-commit run --all-files
git diff --check
```

The exact live runner/command must be recorded after implementation without embedding Cookie values or authentication-state paths that expose account data.

## Review Gates

- Offline implementation review: platform registration, pure parsing boundaries, no private-response code, stop conditions, field minimization and test independence.
- Live review: one keyword, one page, visible browser, no result click, no challenge bypass, required fields and Toutiao-only canonical hosts.
- Authentication review: first login is manual, second start is live-confirmed, state file is ignored and `0600`, evidence contains no credential material.
- Delivery review: fork commit is pushed and reachable before the parent gitlink moves; both worktrees are clean except user-owned runtime directories.

## Rollback Points

- DOM contract cannot reliably separate result title/link from page chrome: stop before store integration and do not weaken selectors into whole-page scraping.
- Login UI cannot produce a stable live-auth signal: keep anonymous search working, mark required-login acceptance incomplete and do not save unverified state.
- CAPTCHA, slider, 403/429 or mandatory-login wall appears during search: stop the live run. During explicit login only, allow manual handling until timeout; do not add navigation retry, automated challenge handling, stealth or private API fallbacks.
- Offline suite or privacy scan fails: do not run the real account regression or push the fork commit.
- Real search cannot produce valid Toutiao links: do not update the parent gitlink or claim completion.

## Delivery

- [x] Dispatch Trellis implementation review after all code and real-regression evidence are ready.
- [x] Commit and push MediaCrawler `main` with a Conventional Commit (`815ce9332c74097914c61899a0e37ea1b60e0af3`).
- [ ] Update the parent submodule pointer, commit parent task artifacts/evidence, then archive the Trellis task only after user review.
