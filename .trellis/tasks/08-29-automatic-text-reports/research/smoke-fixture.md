# C isolated browser-acceptance fixture

Owned test-only files: `backend/tests/topic_report_smoke.py` and
`backend/tests/test_topic_report_smoke.py`. Production routes, shared fixtures,
the released frontend, runtime data and saved user credentials are untouched.

## Launch and isolation

Main owns starting/stopping services and forwards; the implementer did not start
this server. From the frozen Centaurus backend snapshot, with its existing uv
environment:

```sh
cd /tmp/longtian-decoupling-impl.dMCxsd/backend
PYTHONPATH=src:tests uv run --frozen uvicorn topic_report_smoke:create_smoke_app --factory --host 127.0.0.1 --port 46082
```

Use the frontend at exactly `http://127.0.0.1:46081` and its existing isolated
API-base override for `http://127.0.0.1:46082/api/v1`. CORS permits only that UI
origin, GET/POST/PUT and Content-Type; no credentialed CORS, alternate localhost
origin, arbitrary headers or DELETE. The ordinary product Host/Origin/JSON
mutation guards remain active.

`create_smoke_app()` composes `topic_report_fixtures.api_environment`, the actual
`create_app` lifespan, A initial-analysis service, C report service and durable
completion-event handoff. The new report is not precomputed or injected. Each
factory gets its own on-disk temporary SQLite database, synthetic credential
store and synthetic media spool, cleaned after application shutdown. The fake
model transport cannot contact a provider or run a connection test. Platform
worker launch is forbidden by the shared fixture. A separately injected counted
search/open/manual worker raises before browser or collection work. No real
account, real media, runtime database, scheduler task or provider is used.

Availability flags are on for the completed fake A/B/C application; persisted
automatic-analysis authorization remains off. There are no seeded schedules;
normal schedule creation still defaults disabled. Factory construction, startup,
history reads, refresh and polling make no model/media/collection requests.

## Frozen seed and known routes

- Empty fixture setup run: run 1, no results.
- Main history: run 2, result IDs 1–101, synthetic platform IDs 1000–1100.
- Other history: run 3, result IDs 102–103, synthetic platform IDs 5000–5001.
- All-never-started admission: exactly 103 sources, spanning runs 2 and 3.
  Results 8 and 19 have incomplete media inventory; the other 101 complete the
  actual initial-understanding pipeline. The report judges all 101 saved texts:
  96 relevant, 3 irrelevant (results 2–4), 2 uncertain (results 5–6), and 2
  unavailable (incomplete stage-one evidence). These are source counts, not
  verified incidents.
- Legacy history: run 4, result 104, summary 1. It uses real legacy repository
  creation/completion and claim triggers, complete saved input, one relevant
  item and a bounded cited document. This is synthetic historical data, not a
  legacy request executed during the fixture. It is visibly `legacy_completed`,
  excluded from the 103-candidate bulk and from the automatic C report.

Known UI paths:

- Later shared-results page: `http://127.0.0.1:46081/results?offset=100`.
- Main collection detail: `http://127.0.0.1:46081/collection-runs/2`.
- Readable legacy collection detail:
  `http://127.0.0.1:46081/collection-runs/4`.
- Legacy HTTP reads: `/api/v1/search-runs/4/ai-summaries`,
  `/api/v1/ai-summaries/1`, `/api/v1/ai-summaries/1/items`,
  `/api/v1/results/104/legacy-analyses`.
- Read-only counter URL:
  `http://127.0.0.1:46082/api/v1/topic-report-smoke/counters`.

The normal first explicit A admission becomes job 1 and, after normal settlement,
exactly one automatic C report 1. Source page `offset=100&limit=50` includes
result 103 from run 3; its citation remains available in a paginated leaf even
when the current results/source page does not contain it. The 96 relevant sources
form 12 leaves and 3 bounded overview nodes, with a root covering all 96 sources.

## Counter semantics and expected progression

Counters observe the injected operations, not report state. `synthetic_media_calls`
counts actual fake acquisition-worker invocations; `synthetic_initial_calls`,
`synthetic_judgment_calls`, `synthetic_leaf_calls`, and `synthetic_overview_calls`
come from `TextPipelineClient.complete` parsing each actual model payload.
Composition is leaf plus overview; total model is the actual transport call log.
`synthetic_collection_calls` counts attempted fake search calls.
`synthetic_browser_calls` counts attempted fake result-open/manual-page calls;
the separate platform launcher is also fail-closed. `legacy_generation_requests`
counts incoming POSTs to the old generation route, including rejected requests,
so a hidden UI generation attempt is not mistaken for passive history access.
Historical seeded usage is not counted as new runtime requests.

Expected cumulative counts for the exact acceptance sequence below:

| Point | Media | Initial | Judgment | Leaf | Overview | Composition | Total model |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Factory/startup/reads | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Normal automatic report completed | 103 | 101 | 101 | 12 | 3 | 15 | 217 |
| One-off override failed once | 103 | 101 | 202 | 24 | 3 | 27 | 330 |
| Same-prompt explicit retry completed | 103 | 101 | 202 | 25 | 6 | 31 | 334 |

Collection, browser and legacy-generation-request counters stay zero throughout
this sequence. Reads and exact UUID replay do not change any counter. Retrying
with the same prompt reuses 101 judgments and 11 successful leaves; only the
failed leaf and three overview nodes execute. Reused nodes contribute no
historical usage to the retry version.

## Main browser acceptance sequence

1. Start at the later results page and inspect the counter URL: all zero,
   104 stored results, 103 eligible candidates, automatic policy off. Open the
   legacy collection detail/history, then return; no old generation POST.
2. Use the one-click all-never-started initial-analysis action. Confirm the
   existing two-stage disclosure once. Stage one settles 103 processed / 101
   successful / 2 incomplete; C follows automatically without another generate
   action or confirmation. The normal automatic report completes.
3. Inspect separate stage usage, saved prompts, relevant/irrelevant/uncertain/
   unavailable outcomes, later source pages and all leaf pages. Follow the
   frozen saved-text/history citation for result 103 without opening a live
   external platform. Reload and revisit both new and legacy history; counters
   stay at the normal-completion row.
4. Use the secondary report-only new-version control with the exact override:
   `验收：失败一次。仅根据本次保存文本生成报告，保留不确定性。`
   The first leaf returns an invalid source ID exactly once. The leaf stores
   `composition / invalid_citations`; aggregate report status is failed with
   `composition / internal_error`, while saved source judgments and 11 valid
   leaf drafts survive. Shared prompt defaults and initial evidence are unchanged.
5. Explicitly retry that failed version with its same prompt (null override in
   the retry API). A new report completes, preserving both older versions and
   scope. Media, initial and collection counts do not increase. Optional interval
   reports may be tested separately; the table above assumes no extra operations.

## Validation evidence

Local Ruff 0.16.4 formatting and lint passed for both assigned files; local
`git diff --check` passed. The core performed the exact two-file one-way sync and
granted a serialized validation window; no source sync or remote edits occurred
during the following checks from the backend snapshot:

```sh
uv run --frozen ruff check tests/topic_report_smoke.py tests/test_topic_report_smoke.py
uv run --frozen ruff format --check tests/topic_report_smoke.py tests/test_topic_report_smoke.py
uv run --frozen python -m pytest -q tests/test_topic_report_smoke.py --tb=short
```

Results: Ruff passed, 2 files already formatted, **6 tests passed in 13.86s**.
Tests assert the exact cumulative counter table above, source/leaf pagination,
legacy readability/exclusion, passive reads, default authorization off, explicit
UUID replay, same-prompt reuse, unchanged shared prompts/evidence, exact CORS,
temporary database cleanup, forbidden collection/open operations and observable
rejected legacy-generation attempts.

After the gate, local `shasum -a 256` and remote `sha256sum` matched exactly:

| File | SHA-256 |
| --- | --- |
| `backend/tests/topic_report_smoke.py` | `b1d690987b8d66c8a2a07654fa3cd822c10df5cff55ccb126f77ca198111ccd7` |
| `backend/tests/test_topic_report_smoke.py` | `a084780fda09b87094c871daae2834028a15adc92d6254ecd07648c039c090d0` |

The two-file source snapshot is stable and released back to core. Core owns the
merged backend full gate; main owns subsequent actual browser acceptance.

The fixture proves workflow boundaries and transport accounting only. It does
not validate real-platform extraction, genuine multimodal quality, provider
availability, factual correctness of model prose, or production scheduling.
