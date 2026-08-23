# 今日头条适配离线验证结果

Date: 2026-08-24 (Asia/Shanghai)

## Scope

- 本文件记录 MediaCrawler 派生仓库的离线质量门，以及匿名入口、完整适配器运行和前两次人工登录尝试的非敏感诊断。
- 修复后的最终匿名、人工登录及浏览器重启验证另见 `live-validation.md`；本文件不复制任何认证材料。
- 父仓库产品代码、既有 `db_data/`、`logs/` 和 MediaCrawler API/Web UI 未修改。

## Results

- Targeted Toutiao + privacy: `84 passed` after the context-specific manual-challenge wait repair.
- MediaCrawler maintained suite: `194 passed` from `.venv/bin/pytest -q tests`.
- Python compile: passed for `main.py`, `cmd_arg`, `config`, `media_platform/toutiao`, `model/m_toutiao.py`, `store/toutiao`, `database`, and `tests`.
- Pre-commit on every changed/new file: passed.
- `git diff --check`: passed.
- Source scans confirmed that the adapter contains no private-response listener, request replay, HTTP search client, stealth injection, LocalStorage/raw-HTML extraction, authorization header, or persisted forbidden personal-info key. `jtoken` and `search_id` occur only in the explicit removal set and test fixtures.
- Authentication fixtures use a non-sensitive sentinel solely to assert secret-safe logging; no real Cookie value or credential material is present.
- No Python type checker is configured in this repository; `compileall` is the available syntax/import-independent static gate.

## Trellis review fixes

- DOM neighbor extraction now discards an ancestor when it cannot prove the container is bounded to 2,000 visible characters, preventing selector drift from sourcing publisher/snippet/time from a page-wide container.
- `ToutiaoContent` now masks `publisher_name` at the model boundary as well as the DOM normalizer, so alternate callers cannot pass an unmasked visible label into a store.
- Cookie injection failures now replace browser exception details with a credential-free platform error and suppress the underlying cause in user-facing tracebacks.
- Canonical URL validation now rejects scheme-mismatched explicit ports and strips only the correct default port.

## Browser isolation review resolution

The Toutiao crawler now always launches a fresh standard visible Chrome `BrowserContext`, regardless of global CDP settings. It contains no `CDPBrowserManager` path and never calls `launch_persistent_context`; `BrowserAuthStateStore` remains the only cross-restart state boundary. Offline tests assert both that enabled dedicated/existing CDP settings cannot select a CDP launcher and that browser construction calls `chromium.launch()` plus `browser.new_context()` while never calling `launch_persistent_context()`.

## Anonymous live navigation diagnosis

- A single anonymous diagnostic run found that direct Playwright navigation to `https://so.toutiao.com/search` ended with `net::ERR_ABORTED`.
- Navigating once through `https://www.toutiao.com/search/?keyword=龙田街道` returned HTTP 200 and followed the platform's normal redirect to the same `so.toutiao.com` search result page.
- The redirected DOM exposed 39 search jump links and showed neither a recognized challenge nor an empty-result state.
- The adapter now uses only the official `www.toutiao.com/search/` entry and parses the final redirected DOM. It does not catch `ERR_ABORTED`, retry navigation, or fall back to direct `so.toutiao.com` navigation.
- No additional live run or login was performed as part of this repair. The later successful full-adapter regression is recorded separately in `live-validation.md`.

## Full-run Page lifecycle diagnosis

- A subsequent full anonymous adapter run still received `net::ERR_ABORTED` on its single official-entry navigation.
- The successful isolated diagnostic used a fresh blank Page, while the full adapter had first navigated that same Page to the Toutiao homepage for the live authentication check.
- The crawler now keeps authentication and search in the same temporary context but on distinct Pages. It creates the search Page only after authentication/save completes, closes the homepage Page, and binds search to the never-navigated blank Page.
- Offline orchestration tests prove the homepage/auth check stays on the first Page, the search client is rebound to the distinct second Page, and the first Page is closed. The client test separately proves the search Page performs one navigation only and propagates navigation errors unchanged.
- No third live run or login was performed as part of this lifecycle repair. Later successful validation is recorded separately in `live-validation.md`.

## First live login attempt diagnosis

- The first user-operated login run opened the official login entry, but the first DOM login-state poll raced with the page navigation and raised Playwright's `Execution context was destroyed, most likely because of a navigation` error.
- The browser then closed. The user did not complete login and no authentication state was saved.
- Manual-login polling now treats only that exact Playwright context-destroyed/navigation message as an inconclusive state check, waits the existing one-second interval, and checks the live DOM again. It does not retry any page navigation.
- Unrelated Playwright failures still propagate immediately. Offline tests cover both the tolerated navigation race and an unrelated closed-page failure.
- The next user-operated login attempt after this navigation-race repair is documented below.

## Second live login attempt diagnosis

- The second user-operated login run passed the navigation transition, then the DOM live-state check reported an official safety challenge.
- The pre-repair login flow propagated that challenge and closed the browser before the user could handle it manually. Login was not confirmed and no authentication state was saved.
- `ToutiaoLogin` now catches `ToutiaoBlockedError` only inside its explicit manual-login polling loop, logs one credential-free instruction, and leaves the visible browser available while continuing the existing one-second DOM login checks until success or timeout.
- Repeated challenge polls do not repeat the instruction. Timeout raises `ToutiaoAuthenticationError`, and crawler orchestration tests prove no auth-state save or search occurs.
- Search challenge handling is unchanged and remains fail-closed; the adapter does not inspect, automate, solve or bypass a challenge and does not retry navigation.
- No additional live page or login was opened as part of this manual-wait repair. The later successful third attempt is recorded separately in `live-validation.md`.

## Baseline-only limitation

An additional `.venv/bin/pytest -q tests test` run reached `191 passed, 8 skipped` and failed six legacy Redis/proxy integration cases because no Redis service was listening on `127.0.0.1:6379`. The approved validation command is `.venv/bin/pytest -q tests`, which passed completely; no Redis-dependent product code was changed.

Repository-wide `pre-commit run --all-files` also detects and attempts to rewrite unrelated pre-existing file-header, trailing-whitespace, and EOF drift. Those automatic unrelated edits were reverted. The same hooks pass when scoped to every file in this change.

## Live gate handoff

The anonymous search, user-operated official challenge/login, allowlisted state save, and full-browser-restart restore gates were subsequently completed. Only the non-sensitive outcomes are recorded in `live-validation.md`.
