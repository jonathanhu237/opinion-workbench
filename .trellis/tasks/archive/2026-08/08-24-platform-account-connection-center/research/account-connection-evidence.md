# Platform Account Connection Evidence

## Repository baseline

- Parent revision inspected: `195d2749a6f7370cc42908ef5a5b4018514f95e2`.
- MediaCrawler revision inspected: `1b89c8f841d61d8f23020fa723fcb8010cda3d8c`.
- The parent and submodule working trees were clean before this planning task; only this task
  directory is currently untracked.

## Existing product boundary

- `backend/src/longtian_api/main.py` creates a small FastAPI application with no lifespan,
  database, browser, or worker service.
- `backend/src/longtian_api/api/router.py` registers only the versioned health router.
- `frontend/src/routes/home.tsx` is the current local-service health screen.
- `frontend/src/app/providers.tsx` already provides the singleton TanStack Query client.
- The initialization decision in
  `.trellis/tasks/08-24-initialize-react-fastapi-app/research/mediacrawler-dependency-decision.md`
  requires FastAPI to invoke MediaCrawler as a controlled subprocess rather than importing
  its global configuration/runtime into the product process.

## MediaCrawler authentication evidence

- `cmd_arg/arg.py` exposes only `search`, `detail`, and `creator`; the historical
  `auth_validation` runs set `config.CRAWLER_TYPE` directly and therefore are not a stable CLI
  contract.
- `media_platform/weibo/core.py` already performs an online `WeiboClient.pong()` check, falls
  back to `WeiboLogin`, updates mobile cookies, and checks again. Unknown crawler types happen
  to skip collection, but a failed post-login check is not currently a reliable process-level
  failure.
- `media_platform/weibo/login.py` keeps the official SSO page visible but also opens a separate
  QR image viewer and exits with `sys.exit()` on several failure paths. The connection center
  needs a visible-Chrome-only mode and stable result semantics.
- Weibo, Douyin, Kuaishou, and Xiaohongshu core modules use `CDPBrowserManager`; Toutiao
  intentionally ignores CDP and launches a fresh visible context before proceeding directly
  to search.
- Archived real-browser regressions establish that Weibo, Kuaishou, and Xiaohongshu can restore
  a minimal allowlisted authentication state in an isolated browser, while Douyin retained its
  session through its dedicated profile. These results validate the online probes but do not
  establish a product connection-center contract.

## Browser ownership findings

- `tools/cdp_browser.py` can wait for Chrome's existing-browser remote-debugging port and connect
  to the first existing context.
- In existing-browser mode it does not currently open Chrome or the remote-debugging settings
  page when the port is unavailable; it only waits and logs instructions.
- Its current cleanup closes the selected `BrowserContext` and calls `browser.close()` before
  skipping only process cleanup. Because the selected context may be the user's everyday
  default context, that ownership boundary is unsafe for this product.
- `tools/browser_launcher.py` uses `--remote-debugging-address=0.0.0.0` for program-owned browser
  launches. The product contract requires loopback-only debugging.
- Authentication against the user's Chrome must therefore track and close only task-created
  pages, never close the borrowed context/browser, never terminate an unowned Chrome process,
  and never silently fall back to a separate browser.

## Derived implementation constraints

1. Add a formal authentication-only CLI mode to the derivative; never rely on an unknown type
   falling through collection branches.
2. Authentication-only mode must enforce CDP existing-browser, visible UI, no proxy, no content
   collection, and no explicit Cookie-state export.
3. The subprocess must expose a small versioned, secret-free status protocol; FastAPI must not
   parse or return ordinary MediaCrawler logs.
4. FastAPI owns concurrency, timeout, cancellation, safe error translation, and in-memory status.
5. React owns presentation and polling only; it never receives browser credentials or QR data.
6. Real acceptance must leave a pre-existing Chrome window/tab open after both success and
   failure cleanup.
