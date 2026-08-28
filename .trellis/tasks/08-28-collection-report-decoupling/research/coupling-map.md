# Collection / Analysis / Report Coupling Map

Inspected locally on 2026-08-28 against commit `00e6973`. This is planning
research, not an approved technical design or implementation record.

## Existing Data and Control Boundaries

| Boundary | Repository evidence | Decoupling implication |
| --- | --- | --- |
| Collected identity | `backend/src/longtian_api/database.py:1200` defines a unique platform/content-ID pair; `:1222` stores per-run membership. | Reuse the global content identity, retaining source-run links for provenance. A separate duplicate content store is not required by the user request. |
| Mutable observations | `backend/src/longtian_api/repositories/search_runs.py:346` updates saved source attributes when observed again. | A collection-run ID does not itself represent an immutable historical content version. Freeze source/evidence material at analysis/report admission. |
| Historical rules | `backend/src/longtian_api/database.py:1160` keeps run name/terms but the live rule FK becomes null on deletion. | Never infer old scope from a newly edited rule or group unrelated orphaned runs by a null FK. Historical reports must remain readable. |
| Summary admission | `backend/src/longtian_api/repositories/ai_summaries.py:201` reads one run, rejects active/paused parents and sources outside 1–100, then copies every linked result. | Selecting multiple runs/materials requires a distinct admission/snapshot contract; merely moving the UI does not remove run scope. |
| Report ownership | `backend/src/longtian_api/database.py:110` stores one source run/platform on each report; `:150` makes each item analysis a child of a report. | Independent analysis must own its lifecycle outside a report. Keep old versions and citation relationships intact during any additive migration. |
| Pipeline | `backend/src/longtian_api/services/ai_summaries.py:150` performs cache lookup, acquisition/analysis, then composition. | Extract an independently admitted analysis operation and a composition operation that only reads frozen prepared evidence. |
| API | `backend/src/longtian_api/api/v1/ai_summaries.py:70` creates/lists reports under a search run. Read-by-report-ID already exists at `:102`. | Independent report listing/creation and a deliberate legacy compatibility policy are needed. Existing history reads are useful to preserve. |
| UI contract | `frontend/src/routes/collection-run-detail.tsx:286` embeds the report UI; `frontend/src/routes/collection-ai-summary.tsx:269` verifies the selected report against one run/platform. | Any independent report flow needs a different source contract and source-specific opening controls, not just a new navigation link. |

## Analysis Reuse Is Context-Specific

- `backend/src/longtian_api/services/ai_analysis.py:102` defines context as rule
  name and ordered terms. The prompt asks whether a source is relevant to that
  monitoring scope, rather than assigning a universally reusable category.
- `backend/src/longtian_api/repositories/ai_summaries.py:311` hashes the source
  observation, rule name/terms, configuration revision, endpoint/model,
  analysis/input versions and extractor version. Report-composition input
  likewise contains a single monitoring scope (`services/ai_analysis.py:285`).
- `backend/src/longtian_api/repositories/ai_summaries.py:399` only reuses canonical
  completed evidence and refuses older evidence after a newer acquired input
  fingerprint is known. Do not weaken this protection during extraction.
- An unchanged live rule ID is insufficient proof of context compatibility if
  its terms have been edited. Different rules can also have different criteria
  for the same source. Mixed-rule/custom-topic reports therefore need an explicit
  product meaning and a strategy for context-dependent judgments.

## Prepared Material Is Not a Raw Media Archive

- `backend/src/longtian_api/repositories/ai_summaries.py:62` persists saved text,
  readiness, fingerprints and bounded media metadata. Asset locators are removed.
- `backend/src/longtian_api/services/content_enrichment.py:189` cleans the owned
  per-item staging after acquisition use. Existing policy intentionally does not
  retain temporary media bytes in report storage.
- Another report may use completed text evidence without acquisition or item
  model calls. A new media judgment after a context change/force refresh may
  require reacquisition. Do not promise offline reanalysis of media that is not
  stored, or silently add a permanent media archive.
- Source opening/acquisition proves `(run_id, result_id)` membership and checks
  active/paused collection ownership
  (`backend/src/longtian_api/repositories/search_runs.py:555`). Keep a valid origin
  per selected source, including XHS's existing controlled reopening path.

## Time and Capacity Constraints

- Collection runs and observations have normalized timestamps. Source publication
  time is only `published_at_text`, which can be relative/unstructured
  (`backend/src/longtian_api/schemas/search_runs.py:91`). A date filter must state
  whether it selects collection observations or actual publication times.
- `backend/src/longtian_api/schemas/search_runs.py:106` exposes global
  `first_seen_at`/`last_seen_at` separately from per-run observation timestamps.
  `backend/src/longtian_api/repositories/search_runs.py:301` deduplicates globally;
  the insert at `:310` sets first-seen time, while later observations update
  `last_seen_at` at `:350`, not first-seen time. Per-run observation membership
  is separately stored at `:373`.
- User-approved report-window basis: global first entry into results, not publication
  time. This fits reports about new discoveries and prevents repeat collection
  from making old posts look newly discovered. Trade-off: a post observed again
  today but first collected earlier belongs to its original window, and an old
  post first found today can be included today. Reports must preserve the source's
  actual/unknown publication-time context and never call these new incidents.
  The user confirmed these selection semantics during planning; this is not
  yet an implemented date filter or approval to leave planning.
- The current 100-source and 120,000-character composition bounds are validated
  in `backend/src/longtian_api/services/ai_analysis.py:285` and subsequent prompt
  construction. Cross-run selection must not silently truncate or bypass these
  per-request limits. The proposed new bounded multi-request strategy lives in
  `../design.md`; the old whole-report cap is not a user-approved restriction.

## Invariants to Carry into the Design

The owning contract is `.trellis/spec/backend/ai-summary-guidelines.md`:

- No paid work on GET, page entry, refresh or restart. New analysis automation is
  a product decision, not a consequence of making analysis independently callable.
- Idempotent, revision-bound explicit requests; settings/AI lease and browser
  ownership must be handled separately. Text-only report composition consumes
  frozen evidence and needs no browser reservation.
- Preserve source attribution, strict model output/citation validation, truthful
  incomplete/uncertain/error states, token accounting and old report snapshots.
- Additive migration, settled cancellation/SQLite work, no destructive historical
  rewrite, no automatic paid repair/retry and no new media retention policy.
- Existing regression seeds: `backend/tests/test_ai_summaries.py:26`, `:188`,
  `:319`; `backend/tests/test_ai_summary_repository.py:69`, `:138`, `:169`.

## Product Decision Inventory

The user clarified the intended product flow after the initial research:
monitoring rules are configuration only; scheduled collection references a rule
and writes results; the downstream module is "Results and Analysis", where
users provide their own LLM instructions to judge relevance and further analyse
only relevant results. The latest clarification fixes the order: understand and
summarise all new sources first, then use their saved text for topic relevance,
analysis and reporting. Do not apply a relevance gate before stage one or turn
the earlier single-rule-per-report recommendation into an approved restriction.
The user subsequently confirms automatic stage-one work after collection,
editable prompts for both, and prompt edits applying
only to future executions with explicit historical reruns. The updated
two-stage findings are in `custom-analysis-prompts.md`. Cross-run report selection
by first-entry time is also now confirmed, as is the initial scheduling policy.
The latest clarification supersedes the earlier on-demand report policy:
reporting is automatic and uses completed initial analyses without another click.

1. **Confirmed:** fixed minute/hour intervals, skipping due occurrences while
   busy, and no replay of missed offline rounds. Preserve manual-verification
   pauses. See `scheduling-boundaries.md`; no scheduler has been activated.
2. **Confirmed:** retain pending new-result work across collections independently
   of the `new` flag, with failed/incomplete/interrupted attempts visibly distinct
   and explicitly retryable. Pre-existing unanalysed history is user-selected,
   not automatically swept into paid work. This approved policy replaces the
   earlier, unapproved all-unprocessed-content proposal. An older completed
   summary is not newly collected content merely because the prompt was edited.
   Keep automatic admission separate from analysis-cache compatibility and
   preserve known-change protections.
3. **Confirmed:** two editable shared prompt defaults in Results and Analysis.
   Automatic stage one uses its default;
   automatic stage two uses its saved default; optional user-directed per-request
   overrides do not change that default unless explicitly saved. No editor is a
   prerequisite for automatic generation. Defer per-collection-task assignments and
   a named template library. This configuration scope is now approved; see
   `custom-analysis-prompts.md`.
4. **Confirmed:** one-click initial analysis belongs to stage one and covers all
   records not yet initially analysed, including explicitly selected history.
   It saves each record's understanding independently before a report consumes it.
   Stage two is now a separately persisted automatic report operation. The earlier
   stage-two interpretation was incorrect. Retain automatic new-result processing
   and separate retries; share queue/idempotency rather than duplicate work.
5. **Confirmed:** report automatically from completed initial analyses, using
   actual available evidence and truthful coverage without a second click.
6. **Confirmed on 2026-08-29:** one report after each initial-analysis task has
   attempted all its frozen records, using its successful saved outputs. The
   bounded aggregation proposal is in `../design.md`; automatic generation does
   not imply unlimited context, silent truncation or bypassed call bounds.

## Follow-up Evidence: Periodic Collection and New Content

- `backend/src/longtian_api/schemas/monitoring_rules.py:17` has no schedule
  settings; `backend/src/longtian_api/schemas/search_batches.py:77` accepts a
  rule, platforms and result cap to start one batch. The inspected backend
  lifecycle (`backend/src/longtian_api/main.py:75`) contains no periodic
  collection scheduler. UI `refetchInterval` calls are read polling, not crawls.
- `backend/src/longtian_api/services/search_batches.py:167` restores a durable
  paused batch without browser work. At `:216`, starting a batch claims the
  shared browser and rejects contention. A future scheduler must not treat
  polling/restart as permission to resume paused browser work or bypass human
  verification. Auto collection is new product scope, not an existing switch.
- `backend/src/longtian_api/repositories/search_runs.py:301` deduplicates against
  the global content identity. At `:373`, per-run `discovery_kind` is `new` only
  when the global content row was inserted. A source can be `repeated` but have
  never been analysed, or have failed analysis earlier. Therefore this field
  cannot be reused as an analysis queue/cursor.
- `backend/src/longtian_api/repositories/ai_summaries.py:171` reconciles queued or
  running legacy summaries to `interrupted` at startup; it does not automatically
  repeat the paid request. At `:328`, pending items belong to a specifically
  created summary. Neither this state nor cache lookup at `:399` is a global
  list of new content eligible for automatic understanding. A new persistent
  pending list must distinguish unstarted new-content work from historical
  backfill and failed/interrupted attempts, whose replay can incur new cost.
- The user-defined progression is collection -> saved candidate material ->
  all-new-result content understanding -> saved textual evidence -> text-only
  topic relevance/analysis/reporting. The UI can keep the latter steps together
  while their execution, retry and persisted ownership remain separate.
- The existing media-completeness/retention constraint above still applies:
  search results do not prove complete offline model input. Do not promise
  browser-free analysis or add permanent media storage without an explicit
  preparation/retention design. Saved-evidence composition remains browser-free.
- Planning now separates shared initial analysis, scheduled collection and
  automatic reports into three child tasks; `../prd.md` owns the mapping and
  integration contract. All remain planning; none has been started.

No implement/check agents, product changes, database migrations, browser actions,
provider requests or build/test workloads were run during this research.
