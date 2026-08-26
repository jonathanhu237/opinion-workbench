# 平台搜索

## Goal

Give the local operator one real collection loop: choose an enabled monitoring rule, run a bounded
Toutiao search through the approved local Chrome session, and receive durable original-content
links that clearly distinguish newly discovered content from historical content found again. This
creates the product foundation for later scheduled collection without pretending that scheduling,
AI analysis, or the other four platform-search integrations already exist.

## Background

- The account center can check Weibo, Douyin, Kuaishou, Xiaohongshu, and Toutiao through one
  persistent MediaCrawler worker connected to the user's approved Chrome debugging session.
- Monitoring rules are persisted in product SQLite. Enabled rules contain ordered terms with
  implicit OR semantics; collection must search every accepted term independently.
- MediaCrawler remains the isolated platform engine. FastAPI owns product orchestration, safe public
  errors, normalized business data, SQLite, and the React API.
- The capability audit found that Toutiao is the only current platform with a minimal typed
  discovery model, visible-page search adapter, focused parser/URL/store tests, explicit search
  failure categories, and recorded real-search evidence. Its recorded live proof used a fresh
  browser context, so the approved borrowed-Chrome path still needs its own implementation and
  manual acceptance.
- The long-term product needs daily discovery, but this task deliberately proves a manual one-shot
  loop before scheduling and unattended execution are introduced.

## Requirements

### Search setup and execution

- Add one real `采集任务` destination. The operator selects an enabled persisted monitoring rule;
  the search form never asks them to retype or redefine rule terms.
- Platform belongs to the collection operation, not the monitoring rule. The first delivery exposes
  Toutiao as the only executable search platform.
- A run is manual and one-shot. It searches rule terms sequentially with OR semantics and does not
  mutate the saved rule.
- One run accepts at most 20 terms. A larger rule is rejected before browser work with clear Chinese
  guidance to split the rule.
- The operator may set `max_results_per_term` from 1 through 50; the default is 10. The limit is a
  run parameter, not part of the saved rule.
- FastAPI starts the operation asynchronously, persists truthful progress, and supports explicit
  cancellation. Browser-unsafe platform checks and searches are globally serialized.

### Durable results and deduplication

- Search runs, rule-name/term snapshots, progress, terminal outcomes, and normalized results are
  persisted in `runtime/longtian.sqlite3` and survive page refresh or backend restart.
- A content item is globally unique by `(platform, platform_content_id)`. Finding it again must not
  create another content row.
- Every run still records which unique content items it observed and every rule term that matched
  them. An item inserted during the current run is `new`; an item that existed before the run is
  `repeated`. A second matching term in the same run does not change a new item into a repeated one.
- Repeated items remain visible in the current run and are labeled `历史内容再次命中`. Run summaries
  report separate new, repeated, and total unique-result counts.
- Repeated observations update `last_seen_at` while preserving `first_seen_at`. Mutable normalized
  fields may be refreshed without overwriting useful stored values with empty platform fields.
- Results expose at least platform, content type/ID, title or usable text, safe canonical original
  URL, matched source terms, first-seen time, last-seen time, and Toutiao's visible publication-time
  text when present. A relative or vague platform time string is never represented as a precise
  parsed timestamp.

### Truthful outcomes and safety

- The product distinguishes queued/running, completed with results, completed empty, login required,
  manual challenge required, platform blocked/rate limited, structure changed, browser unavailable,
  timeout, cancellation, and internal failure. None may become a false successful empty run.
- Official login, slider, SMS, or safety challenges remain visible and manual. The system does not
  bypass them, retry a blocked search, or fall back to a private/internal API.
- Search uses only task-created pages in the borrowed default Chrome context. It never closes the
  user's browser, context, or pre-existing tabs and never installs context-wide stealth scripts.
- FastAPI runs MediaCrawler outside the API process. React never sees child frames, Cookies,
  LocalStorage, authentication headers, raw platform bodies/HTML, QR data, browser-profile paths,
  raw child output, or raw exception text.
- The completed platform-account and monitoring-rule behavior remains compatible.

### Interface behavior

- The new page inherits the existing Shadcn-based application shell, palette, typography, focus
  behavior, and responsive conventions. It does not introduce a replacement color system, fake
  telemetry, decorative dashboard metrics, or placeholder destinations.
- The page shows a compact start form, the active run and real progress when present, durable run
  history, and a deep-linkable run detail with new/repeated filters and original links.
- Empty and failure states explain the next action in natural Chinese. Login-required outcomes point
  the operator to the existing platform-account flow; technical details remain hidden.

## Acceptance Criteria

- [ ] From `采集任务`, the operator can select an enabled rule with at most 20 terms, keep or change
      the 1–50 per-term limit, start a Toutiao run, and see an accepted durable run without blocking
      the HTTP request.
- [ ] Every accepted term is searched independently and results preserve all matching source terms;
      the saved monitoring rule remains unchanged.
- [ ] The run and result history survives refresh/reopen, and a backend restart reconciles any stale
      active row to a truthful terminal failure instead of leaving it permanently running.
- [ ] Re-running the same search does not duplicate content rows. The second run reports existing
      items as repeated, updates their last-seen evidence, and keeps first-seen evidence unchanged.
- [ ] Duplicate content found by multiple terms appears once in run results with all matched terms;
      run new/repeated/total counts remain internally consistent.
- [ ] Every result link is an allowlisted canonical Toutiao HTTP(S) URL and no credential, raw page,
      profile, command line, child output, SQL/path, or unmasked identity data crosses the API/log/
      evidence boundaries.
- [ ] Empty, login, challenge, block/rate-limit, structure drift, browser unavailable/disconnected,
      timeout, cancellation, and internal failure are observably distinct and do not produce false
      success.
- [ ] Search and account checks cannot overlap. Cancellation/shutdown closes only task-owned search
      pages/processes and leaves the user's Chrome and pre-existing tabs usable.
- [ ] Backend, frontend, MediaCrawler, submodule, cross-layer, and real-browser gates pass without
      regressing account checks or monitoring-rule CRUD.

## Out of Scope

- Daily schedules, unattended execution, retry/backoff, catch-up runs, and automatic continuation
  after restart.
- Weibo, Kuaishou, Douyin, and Xiaohongshu product-search integration. Evidence-based expansion
  order is Weibo, Kuaishou, Douyin, then Xiaohongshu.
- AI sentiment/risk classification, summaries, suggested handling, alerts, reports, and case
  workflow.
- Comment crawling, creator profiles, media downloads, word clouds, broad pagination, and historical
  backfill.
- Automated CAPTCHA/slider/SMS handling, stealth tooling, account pools, challenge retries, private
  API replay, or signature reverse engineering.
- Result deletion/retention management and recurring-task configuration UI.

## Technical Notes and Risks

- Detailed current-code evidence and platform ordering live in
  `research/platform-capability-audit.md`.
- The existing generic Toutiao crawler deduplicates within its crawler loop and persists through
  MediaCrawler stores. The product path must instead emit normalized per-term observations to
  FastAPI so cross-term provenance and product-owned SQLite remain authoritative.
- `.trellis/spec/backend/browser-search-adapter-guidelines.md` remains the contract for standalone
  fresh-context adapters. The product borrowed-browser orchestration requires a separate explicit
  contract and must not silently weaken either lifecycle.
