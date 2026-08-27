# Search-First Multimodal Summary Design

Status: revised after the user accepted search-first scope on 2026-08-27; fresh downstream final review pending. Checked AI configuration is unchanged.

Rule-editor amendment: the user accepted separate monitoring-object/issue-keyword inputs, preview and object-only search when issues are empty. The bounded contract is in `../08-27-monitoring-rule-combinations/design.md`; its final review authorizes only that child, not automatic downstream media/summary work.

## Boundary and Flow

Keep the current React/FastAPI/SQLite split and MediaCrawler subprocess. Extend downstream behavior, not search result payloads or collection completion handlers.

```text
Monitoring rule: separate object/issue lists -> generated full-query preview
  -> platform search -> existing deduplication -> visible candidate leads
  -> optional manual Generate summary for one terminal collection run
  -> frozen full-run source/context/configuration snapshot
  -> compatible completed result? reuse : bounded media enrichment -> one LLM call
  -> related / unrelated / uncertain, with input failures and request failures separate
  -> same user-requested job composes relevant saved evidence -> cited summary
```

- Initial UI scope is one terminal collection run; partial collection runs may use their existing results, with that coverage visible. Batch pages retain links to individual runs; batch-wide or cross-day summary is deferred.
- Extend the existing editor with required `监控对象` and optional `舆情关键词` plus preview; no arbitrary Boolean editor, shared dictionary or AI keyword generation. Empty issues leave objects unchanged; otherwise compose ordinary platform queries such as `龙田街道 积水`, not guaranteed strict AND matching. The rule child preserves old phrases as objects with empty issues, adds issue-list persistence and returns derived effective `terms` to unchanged collectors. Keep 100-query saving/20-query execution limits, frozen snapshots and dedup. Search results remain leads; no independent screening delivery.
- The application never automatically starts a new AI job at startup, after search, on route entry or refresh. Job polling resumes display, not execution. No new global dashboard, provider manager or categorization form.
- Five-platform enrichment paths and live gates: `research/platform-media-plan.md`. Model payload, bounds and output schemas: `research/model-transport-contract.md`. Those proposals must be implemented consistently by both sides of each boundary.

## A. Configuration and Credential Ownership

- New `/ai-settings` route, sidebar label `AI 配置`. Three labeled shadcn inputs: `API Key`, `Base URL`, `模型名称`; actions `保存`, `测试连接`. Preserve current theme, typography and shell.
- One `ai_settings` SQLite row (`id=1`): normalized Base URL, model, opaque secret reference, revision, updated time. Do not put plaintext key or secret-derived hashes in SQLite, public configuration, job snapshots or logs.
- A small injectable secret store writes a randomly named regular file inside backend-owned `runtime/secrets/ai/`. On current POSIX targets enforce directory 0700/file 0600, current owner, exclusive creation and no symlinks. Derive runtime from the injected database path; tests cannot use production runtime. Fail closed if the required protection cannot be established. No claim of untested Windows ACL support.
- This is a permission-protected plaintext secret file, not an encrypted vault. It avoids key exposure in ordinary SQLite exports but does not protect against the same OS user, administrators or full-runtime backups. Document that boundary and exclude secrets from every sync/export.
- Replacement transaction: create/fsync new secret file; commit the new reference in SQLite; only then remove the superseded owned file. If database commit fails, retain the old key/reference and clean only the new file. A crash may leave an orphan; cleanup must use exact owned-file records, not a recursive runtime wipe.
- An omitted/null key means retain the existing one only at the same normalized Base URL. Blank keys are invalid; changing any Base URL component requires re-entry. Unchanged saves keep revision; changing settings or replacing a key increments revision. Missing/corrupt secret store is a configuration error, not an empty successful configuration.
- GET returns `{base_url, model, has_api_key, revision}` with unset fields represented explicitly. PUT returns the same projection, never the key. Test uses the saved revision, rejects dirty/stale configurations, and sends a synthetic text request only.
- Newly typed key stays solely in transient form/request state; use a direct save boundary so TanStack mutation variables/cache do not retain it. Clear the key field after submission; no localStorage/sessionStorage/query persistence. Do not log bodies or validation inputs.
- New AI mutation routes require JSON, validated local Host/Origin (same-origin or explicitly configured local frontend origin); reject cross-site/`null` browser origins and do not introduce wildcard CORS. Local non-browser clients remain possible. This is a loopback single-user tool, not public-server authentication.

## B. Enrichment Contract

- Backend command takes a stored source identity, its first observed matched term where necessary, a generated request UUID and bounded media budget. It does not accept arbitrary client URLs, paths or raw platform identifiers as a substitute for repository lookup.
- Add a distinct typed enrichment IPC command/result. Do not append full text/media into the search-only wire schema or route through generic crawl/detail/comment loops.
- Worker owns exact-ID source verification, authenticated access and task-owned tabs. URLs/tokens remain ephemeral inside the worker; platform credentials never leave it. Use approved CDN/host validation and bounded streaming transfers, not bulk browser-storage reads or a generic download proxy.
- Return an `EnrichedContent` projection: source identity, bounded full text, text coverage, per-asset kind/MIME/byte count/hash, media coverage/reason, extractor version and acquisition time. No author identifiers/profiles, signed URLs, headers or raw page state. Absent media is different from failed/unknown media detection. Metadata must fit the existing 64-KiB UTF-8 IPC budget; oversized normalized text/metadata uses an owned, bounded manifest handle with the same path/hash validation, never line truncation.
- Media files use an operation-owned temporary directory and opaque asset handles. The backend derives paths from validated UUID/asset IDs, rechecks regular-file containment/size/hash, and never trusts a child-supplied absolute path. Keep large binary data out of line-oriented IPC. Handles are not public file-serving endpoints. Use bounded, network-disabled local-file `ffprobe` inspection for MP4 codec/audio metadata; do not invoke ffmpeg transcoding. Missing probe/unknown required media properties are incomplete input, not established support.
- Enrichment participates in the existing browser coordinator under a distinct owner. Do not close/detach the user's browser or unrelated tabs. Login/challenges stay manual; no bypass or generic retries. Always release ownership and clean owned temporary files on failure/cancellation.
- During a summary job's content-analysis phase, reserve browser ownership for the serial enrichment sequence; do not allow search/account checks to steal it. Release ownership before text-only composition. Compatible evidence reuse requires no post reopening; configuration tests and final composition need no browser ownership.

## C. Job, Data and Reuse Model

Use the checked lifespan-owned AI-operation lease shared by tests and the manual summary pipeline. No Redis/Celery, separate worker service or generic workflow framework. One application process is required, consistent with existing browser ownership.

- `ai_summary_runs`: unique request UUID, source run FK, frozen context/configuration/prompt versions, state/phase, counts and timestamps, final eligible item references/input hash and validated structured summary. One row owns the complete manually requested pipeline and output version.
- `ai_summary_items`: ordered unique `(summary_run_id, content_id)`, frozen source projection, observation hash, enriched text/media metadata, input hash, state, model decision/reason/evidence, error code and optional `reused_from_item_id` FK. No standalone screening-run tables or public screening API.
- Keep source snapshots immutable and source FKs for traceability. Counts and references are backend-derived. Media metadata JSON has one typed decoder; no arbitrary dictionary/pickled state. No additional media/blob table is required initially.
- Migrations are additive after the actual checked schema. Configuration currently ends at v8; the rule-composition child next adds issue-term storage. Summary later adds run/item tables after the then-current version; media retrieval needs no product migration. Re-read versions before implementation and never rewrite released migrations. Follow SQLite connection-per-operation, parameter binding and short transactions.
- Job state: `queued -> running -> completed | failed | cancelled | interrupted`. Completion means the bounded iteration ended, not that every item succeeded. Item states include `pending`, `running`, `completed`, `input_incomplete`, `failed`, `cancelled`, `interrupted`; only completed items can contain an LLM decision (or reference a completed cached item).
- Phase is `analysing` then `summarising`. Final composition starts only as part of this explicit summary request, never from a background post-collection hook. No relevant evidence yields a truthful completed no-relevant-evidence result without a composition call; preserve all exclusion/error counts. A composition error retains completed item evidence for a later explicit retry.
- New POSTs have a client UUID per user intent; replay returns the same job, conflicting reuse returns 409. Snapshot all source rows in one transaction before processing and never use the UI's paginated subset. Empty/active source runs are rejected. Configuration saves are rejected while an AI operation uses it, avoiding secret/configuration rotation mid-call.
- Freeze the collection run's rule name/terms, not a subsequently edited/deleted rule. A new collection captures new rule context. Display this historical scope; changing today's rule cannot silently rewrite a past analysis.
- Reuse checks source identity, observed title/snippet/type hash, frozen context, config revision/endpoint/model, prompt and extractor/input schema versions, plus previously observed full-text/media hashes. Exclude ephemeral signed URLs, last-seen timestamps and relative publication display text. A content ID alone is insufficient (`repositories/search_runs.py:196`).
- Normal summary generation may reuse the last compatible completed item evidence without reopening a post; this does not prove remote freshness. Known changes require enrichment and a new judgment. An explicit force-refresh option in the same generation action ignores item cache. Successful `uncertain` judgments may be reused; missing input, provider failures and interrupted attempts may not.
- Startup marks unfinished AI work interrupted without a browser/model call. Shutdown cancels owned tasks, bounds cleanup and preserves completed items. A new user-requested generation reuses compatible evidence and retries the rest; it may explicitly force refresh. Never copy search-batch auto-resume semantics into AI jobs.

## D. API and UI Shape

All endpoints live under `/api/v1`, use strict request/response models, Annotated dependencies and existing sanitized error envelopes. Blocking SQLite/filesystem work runs off the async event loop.

| API | Contract |
| --- | --- |
| `GET /ai-settings`, `PUT /ai-settings` | Read/update one non-secret configuration projection |
| `POST /ai-settings/test` | Explicit bounded test of saved revision; no post/media inputs |
| `POST /search-runs/{run_id}/ai-summaries` | `{request_id, force_refresh}`; 202 with full frozen scope; owns analysis and composition |
| `GET /search-runs/{run_id}/ai-summaries` | Read summary history/latest status only |
| `GET /ai-summaries/{id}` | Job phase, counts, source coverage and stored report if available |
| `GET /ai-summaries/{id}/items` | Paginated typed analysis outcomes and evidence supporting this summary |
| `POST /ai-summaries/{id}/cancel` | Stop owned pending work; preserve completed evidence |

- Keep original collection results visible and usable. Add one `生成汇总` action with progress/cancel and the report beneath it. Show concise coverage and inspectable per-item reasons/errors without a new screening dashboard or prerequisite related-results page. Keep the existing new/repeated collection semantics separate.
- A start confirmation states the full run count, destination host/model, and that text/media will be sent to that provider and may consume quota. No decorative security badges or lengthy tutorial. Missing configuration points to `AI 配置`.
- Use existing shadcn Button/Field/Input/Badge/AlertDialog, RHF+Zod forms and TanStack Query for non-secret resources. URL owns selected summary/version and item page when needed. Poll only active jobs; never issue generation from effects. Errors remain adjacent to controls.
- `生成汇总` is available for a terminal nonempty collection run with saved configuration and available admission. No prior AI result is needed. Before any media/model work, reject runs above 100 unique sources. Do not silently select the current page/new-only rows; source-level scope is explicit.
- Final composition makes one text-only call on completed relevant evidence, unique by stable source, with at most 120,000 input characters. Check this bound before that call; failure retains prior item evidence. Empty eligible sets make no composition call. The complete operation can make N uncached-item calls plus one composition call, not one giant multimedia request; each item media is uploaded only once. Larger/cross-run reporting is deferred.
- Render summary as escaped prose and backend-built references. For XHS links, reuse the existing source-run `打开原文` action so canonical URLs do not bypass ephemeral-token reopening. Other platforms use validated stored canonical links. Old summaries keep their original source versions after later generation/refresh.

## Validation, Rollout and Rollback

- Mock-based tests cover migration/reopen, secret atomicity/non-disclosure, API status/code pairing, origin/destination guards, media completeness/ownership/path validation, SSE bounds, verdict validation, idempotency, immutable scope, reuse invalidation, restart/cancel and reference integrity.
- Live gates separately prove the five narrow media extractors and configured-model image/video/audio understanding. No key from chat, runtime database, authentication files or raw payloads enter remote sync/test artifacts.
- Develop locally, rsync source only one-way to Centaurus, test there, forward services for UI checks. Existing daily-browser live acceptance needs the local browser and explicit user readiness; it cannot be replaced by a headless remote mock or silently run locally as a heavy fallback.
- Deploy sequentially with separate activation gates: checked configuration, rule composition, internal enrichment, then integrated manual summary. Standalone screening is deferred. Disable/remove new UI/runners to back out while preserving collection data. Older binaries reject newer schemas, so binary downgrade requires a verified pre-migration backup; never claim automatic downgrade or delete user data.
- Final acceptance is the parent PRD plus all child checks. A passing mock suite is not proof of platform/media availability or trustworthy model judgment.
