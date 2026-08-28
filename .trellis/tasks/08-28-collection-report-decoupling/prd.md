# 采集与报告解耦

## Goal

Separate reusable monitoring rules, scheduled collection, per-record initial
understanding and text-only reporting. Users manage collection independently,
read reusable evidence in Results and Analysis, and control both AI stages'
instructions. One initial-analysis action covers every never-analysed record;
after that task finishes attempting its records, reporting follows automatically
from its successful outputs, with substantive analysis only for relevant sources.

## Background and Confirmed Facts

Planning consent was given on 2026-08-28. On 2026-08-29 the user confirmed the
once-after-task report timing with the example of eight successes and two
failures. These are product decisions, not approval to implement or run models.

The authoritative requirements below supersede the earlier relevance-first
proposal, mandatory manual report-generation/partial-readiness confirmation,
and the assistant's mistaken interpretation of one-click analysis as stage two.
Neither a single-rule-per-report restriction nor the old 100-source product cap
was approved. User dissatisfaction with prior AI output motivates editable
instructions; it does not establish a model-quality diagnosis.

- The existing summary action freezes all results of one terminal search run,
  including its historical rule context
  (`backend/src/longtian_api/repositories/ai_summaries.py:201`).
- One summary operation currently reuses cached item analyses or acquires missing
  source material and analyses it, then composes a text-only report
  (`backend/src/longtian_api/services/ai_summaries.py:150`).
- Content identity is already deduplicated across runs by platform and platform
  content ID; run-to-content links preserve collection membership
  (`backend/src/longtian_api/database.py:1200`).
- Saved item evidence currently belongs to summary records, and reports require
  a single source run and platform
  (`backend/src/longtian_api/database.py:110`,
  `backend/src/longtian_api/database.py:150`).
- Item relevance is evaluated against a rule name and ordered query terms, and
  the cache includes that context, configuration and input/prompt versions.
  A shared content ID or monitoring-rule ID alone does not prove that an old
  judgment is reusable for a new report topic
  (`backend/src/longtian_api/services/ai_analysis.py:102`,
  `backend/src/longtian_api/repositories/ai_summaries.py:311`).
- Analysis and composition prompts are fixed code constants. The item response
  currently requires a relevance decision, reason and evidence summary even for
  unrelated/uncertain sources; only final report composition filters to relevant
  items. AI settings expose endpoint/model/credentials, not editable prompts
  (`backend/src/longtian_api/services/ai_analysis.py:115`,
  `backend/src/longtian_api/services/ai_analysis.py:167`,
  `backend/src/longtian_api/services/ai_summaries.py:192`,
  `backend/src/longtian_api/schemas/ai_settings.py:32`).
- Saved analysis retains text and bounded media metadata, not durable raw media.
  Reusing evidence for another report is possible without another upload;
  reanalysing media for a different context may require reacquisition
  (`backend/src/longtian_api/repositories/ai_summaries.py:62`,
  `backend/src/longtian_api/services/content_enrichment.py:189`).
- The previous summary scope explicitly excluded standalone analysis and
  cross-run reporting. This task revises those boundaries; the previous task
  and its acceptance records remain intact
  (`.trellis/tasks/08-27-ai-opinion-summary/prd.md`).
- Monitoring rules currently contain a name, monitoring objects, issue keywords
  and an enabled flag, with no scheduling fields
  (`backend/src/longtian_api/schemas/monitoring_rules.py:17`). Collection batches
  are explicitly started from a rule/platform selection, and startup restores
  paused ownership without launching browser work; there is no periodic
  collection scheduler in the inspected product source
  (`backend/src/longtian_api/schemas/search_batches.py:77`,
  `backend/src/longtian_api/services/search_batches.py:167`,
  `backend/src/longtian_api/main.py:75`).
- Collection's `new`/`repeated` marker is assigned from whether the global
  platform/content-ID record already existed, not from AI processing state
  (`backend/src/longtian_api/repositories/search_runs.py:301`,
  `backend/src/longtian_api/repositories/search_runs.py:373`).

## Requirements

- **R1 — Independent collection.** Collection obtains and deduplicates candidate
  sources and preserves their origin; producing a report is not required for
  collection results to remain available.
- **R2 — Stage one: all-result content understanding.** Prepare and understand
  every new result, including its available complete text and actual media,
  and save an individual textual summary/analysis. Do not discard a source from
  this stage because it appears unrelated to Shenzhen Longtian. Stage one has
  independent execution, saved results and retry behavior, and must not require
  creating a topic report. Incomplete/failed inputs remain truthful failures,
  not fabricated completed summaries. After collection, eligible new results
  automatically enter this stage; the user need not start each summary manually.
  This automation does not turn a prompt edit, page load or history read into
  an automatic historical reprocessing request. Persist pending new-result work
  independently of a collection run's `new`/`repeated` marker; later collections
  must neither lose that work nor duplicate it. Pre-existing, never-analysed
  historical sources require explicit user selection for their first analysis,
  including when they are subsequently collected again. The all-unanalysed
  initial-analysis action (R14) is an explicit bulk selection, not an automatic
  historical sweep. Save each per-record output independently, then allow the
  separate automatic report stage to consume completed output. Report creation
  or success must not be a prerequisite for initial-analysis success.
- **R3 — Stage two: report synthesis from saved analyses.** Read saved stage-one
  text and aggregate it into a report under the user's instructions, retaining
  the previously requested relevant-only scope (for example, Shenzhen Longtian).
  Topic selection/judgment belongs inside this report action, not a separate
  user-facing third analysis stage. Freeze the input text/evidence versions.
  This stage does not implicitly restart collection, acquire media, upload
  images/video or repeat stage-one content understanding. Text-model work is
  still allowed and accounted for. Report generation follows initial analysis
  automatically, using valid completed outputs without requiring another user
  click or waiting for unsuccessful/unprepared records to become ready. Expose
  actual included/uncovered counts and reasons; partial readiness is not complete
  source coverage. Generate one report after every member of the frozen
  initial-analysis task has been attempted, using that task's saved successful
  outputs. Show progress during analysis; do not rebuild after every record or
  wait for failed records to succeed. Later arrivals do not extend this task.
  Entering Results and Analysis does not itself start either AI stage; report
  generation cannot back-trigger initial analysis or media acquisition.
- **R4 — Cross-run material.** A report can include material originating in more
  than one collection run. Preserve each source's collection provenance without
  using its originating rule as the mandatory user analysis objective. The user
  can select a first-entry-time range across runs, and stage two consumes the
  saved textual summaries of that scope. This measures new discoveries rather
  than source publication time; repeat observations do not reset the time
  membership. The all-unanalysed stage-one action (R14) is independent of this
  report selection and does not require choosing a report time window. Reports
  automatically use completed initial analyses from the just-finished analysis
  task, not the whole accumulated library. Previously approved time-filter
  semantics remain available for explicit scope selection. Capacity is a
  technical design responsibility, not permission to drop completed material.
- **R5 — Preservation and provenance.** Preserve existing collected content,
  historical reports and usable evidence. Later collection, analysis refreshes
  or failed work must not rewrite the material cited by an existing report.
- **R6 — Independent recovery.** Collection, analysis and composition failures
  leave the other stages' saved results intact. Repeating composition alone
  must not upload media or repeat stage-one item understanding. Failed,
  incomplete or interrupted analysis attempts retain their state/reason and
  require an explicit retry; the automatic new-content runner does not silently
  retry them or turn them into successful or unrelated results.
- **R7 — Rules remain configuration.** Monitoring rules describe what to monitor;
  they are not collection executions or report instances. Downstream work keeps
  the rule context actually used without depending on later edits.
- **R8 — Periodic collection.** Collection runs periodically using monitoring
  rules and preserves each execution and its results. Scheduling belongs to the
  collection responsibility rather than requiring a report operation. Users
  configure a fixed interval in minutes/hours. If the previous execution or
  another shared-browser operation is still active, skip that occurrence with
  a visible reason; do not cancel current work or accumulate catch-up jobs.
  After downtime, continue at the next future scheduled time rather than
  replaying missed rounds. Preserve manual-verification pauses and explicit
  recovery. Missed rounds are not guaranteed to be recovered by later collection;
  existing results and already-admitted work are not deleted. No schedule is
  activated during planning.
- **R9 — Results and Analysis.** Collection writes data into results; users can
  inspect each source and its stage-one textual summary, then perform topic
  analysis/reporting from a shared Results and Analysis module without opening
  each collection-run detail. This module owns both AI-stage interactions and
  is not merely a report viewer. Expose pending new-content analysis across runs,
  completed summaries, and distinct unsuccessful outcomes with reasons. Provide
  an "Initial analysis of all unanalysed records" action, per-record progress,
  and automatic report status/results. A separate report-generation click is
  not required. Let users select historical sources individually or through the
  bulk initial-analysis action and explicitly retry failed/interrupted work. Keep
  per-record initial-analysis output separate from report membership: one saved
  record can contribute to multiple reports.
- **R10 — Both stages have editable prompts.** Users can separately customize
  the stage-one content-understanding/summarisation instructions and the
  stage-two topic-relevance/analysis/report instructions. Neither set is the
  monitoring/search rule. Shenzhen Longtian is the motivating example, not a
  hard-coded application-wide location. Both actual instruction versions must
  be inspectable with their resulting output. Results and Analysis manages two
  independent shared defaults: automatic stage one uses its saved default, and
  automatic stage two uses its own saved default without requiring the user to
  fill in an editor for every report. Retain the previously approved optional
  per-request override for user-directed operations; it affects only that
  report and must not become a mandatory step in automatic generation. Changing
  the shared default requires a separate explicit save. Placement of optional
  overrides in the automated flow belongs to design. First-version scope has no
  named template library or per-collection-task prompt assignments. Provider credentials remain
  separate from these business instructions.
- **R11 — Relevant-only topic output, not relevant-only summaries.** Every new
  result is eligible for stage-one understanding. Stage two distinguishes
  relevant/unrelated sources using the saved textual evidence and the user's
  topic instructions; only relevant sources enter the substantive topic report.
  Retain unrelated sources and their stage-one summaries, with an explainable
  relevance outcome. Preserve the distinction between uncertain geography,
  incomplete material and technical failure; none may be silently converted
  into "unrelated" or "confirmed relevant". Both stages may incur model usage;
  the bounded text-only call strategy is specified in design.md.
- **R12 — Prompt provenance and compatible reuse.** Freeze the instructions
  actually used by each analysis. Editing instructions must not rewrite old
  results or silently reuse judgments produced under incompatible instructions.
  Existing reports retain their evidence and prompt provenance. Only compatible
  completed results are reusable, and prompt edits do not automatically trigger
  paid reanalysis. Changing stage-two topic instructions must not invalidate an
  otherwise compatible stage-one content summary; downstream topic results
  must be recomputed/reused according to their own instruction/input versions.
  User-approved default: saved edits take effect for subsequently admitted
  executions using that prompt. In-flight work keeps its frozen version;
  historical results remain unchanged unless explicitly selected for a new
  summarisation/analysis operation. An older completed summary is not new
  automatic work merely because its prompt version differs from the latest.
- **R13 — Evidence-preserving textual summaries.** Stage-one output must retain
  enough source-attributed text to support later topic judgments: key content,
  explicit geographic clues and supporting excerpts, relevant time context,
  meaningful image/video/audio observations and their uncertainties, source
  identity and input coverage. A short abstract alone is insufficient. Do not
  invent missing place names, treat a keyword match as proof of geography, or
  promote source allegations to verified facts. Stage two must expose unknown
  relevance when this saved evidence cannot justify a Shenzhen Longtian match.
- **R14 — One-click stage-one initial analysis.** In Results and Analysis, one
  explicit action admits all records not yet initially analysed, across pages,
  collection runs and never-analysed history, without individual selections or
  repeated page-sized submissions. Use the saved stage-one prompt and preserve
  per-record textual output/provenance. Initial analysis itself does not combine
  topic/report work into its per-record execution; saved successful output feeds
  the separately tracked automatic report stage (R3), with no extra click.
  Coordinate with existing automatic pending work so queued/running records are
  not duplicated. Completed analyses remain
  completed after prompt edits; historical reanalysis is a different explicit
  action. Previously failed/incomplete/interrupted attempts keep the approved
  separate retry path and are not silently treated as never-started work.
  The old 100-source single-run report cap must not truncate or cap this new
  stage-one bulk selection; each individual acquisition/model request remains
  bounded. Live historical/media/model work is not authorized by planning.

## Acceptance Criteria

- [x] **AC01** Collection can complete and its results can be viewed without generating
  analysis or a report as a prerequisite (R1).
- [x] **AC02** All new source items, including those later judged unrelated to Shenzhen
  Longtian, receive inspectable stage-one summaries independently of report
  creation/success; completed compatible summaries serve multiple reports (R2).
- [x] **AC03** Collection completion automatically makes eligible new results available
  to the stage-one runner without a per-item user action. Completed initial
  analyses automatically feed the report runner at the approved cadence, without
  a second "Generate report" click; GET/page load starts neither stage (R2, R3).
- [x] **AC04** With both completed and unsuccessful/unprepared initial analyses, the
  automatic report uses valid completed outputs and exposes actual coverage;
  missing/failed material is not labelled analysed, unrelated or relevant.
  A report failure leaves saved initial analyses available and retrying the
  report makes no new media/initial-analysis calls (R2, R3, R6, R11).
- [x] **AC05** A report can cite prepared material from at least two collection runs;
  time-scoped selection follows the approved first-entry-time semantics, with
  relevance judged using the user-defined topic instructions (R3, R4).
- [x] **AC06** A source first collected outside the selected range is not brought into
  it merely by a repeat collection. An older post first discovered inside the
  range may be included, but its actual/unknown publication time is retained
  and never represented as a newly occurring incident (R4, R13).
- [x] **AC07** Running/retrying stage-two topic analysis and reporting from saved text
  makes no browser/media acquisition, media upload or stage-one model call;
  new text-only model usage remains accurately accounted for (R3, R6).
- [x] **AC08** Previously generated reports and their source links remain readable, and
  later source/evidence updates do not change their frozen citations (R5).
- [x] **AC09** Failed/cancelled analysis or composition does not remove collected
  sources, completed evidence or earlier reports (R2, R5, R6).
- [x] **AC10** Rule configuration can be managed without creating a collection execution
  or report; existing execution/report scope survives later rule edits (R7).
- [x] **AC11** A user-configured collection schedule creates traceable collection runs
  according to the approved timing/overlap policy, without requiring a report
  operation (R1, R8).
- [x] **AC12** A busy browser/current collection causes a visible skipped occurrence,
  without overlapping or cancelling current work. Recovery after multiple
  offline intervals does not start catch-up runs; the next scheduled time is
  in the future. Repeated due checks do not create duplicate executions, and
  manual-verification pauses require explicit recovery (R8).
- [x] **AC13** New eligible material from successive collections is accessible for AI
  analysis in Results and Analysis. A pending new source remains pending after
  a later collection labels it repeated; neither the source nor its work is
  dropped or duplicated (R2, R9).
- [x] **AC14** Installing/enabling the new workflow does not automatically analyse
  pre-existing unanalysed history, including after repeat collection. Explicitly
  selecting historical sources individually or through the all-unanalysed
  stage-one action can create their first analysis without changing their
  first-entry timestamps (R2, R4, R9, R14).
- [x] **AC15** Failed/incomplete/interrupted analysis retains its state and reason,
  with an explicit retry action. Subsequent collection, page reads, startup
  reconciliation or prompt edits do not silently repeat those attempts or
  create a historical backfill request (R2, R6, R9, R12).
- [x] **AC16** A user can provide Shenzhen Longtian relevance instructions and analyse
  collected results without editing the monitoring rule or rerunning collection;
  the model receives those instructions and each saved verdict identifies its
  instruction version (R9, R10, R12).
- [x] **AC17** A user can edit both the all-result summarisation prompt and the topic
  analysis/report prompt separately. Each operation uses its frozen stage's
  instructions, and editing one stage does not overwrite the other stage's
  instructions or an existing operation/result (R10, R12).
- [x] **AC18** Automatic stage-one work from different collection tasks uses the saved
  shared stage-one default, and automatic reports use the saved stage-two
  default without a required per-report edit. A one-off stage-two override appears
  on that report but does not change either saved default; explicitly saving the
  stage-two default affects subsequent requests only (R10, R12).
- [x] **AC19** Unrelated results retain their completed stage-one summary and receive a
  topic relevance outcome/reason, but do not enter the topic report evidence
  set; uncertainty and input failures remain visible and distinct (R11).
- [x] **AC20** Changing the custom instructions requires compatible new analysis for
  reuse, leaves old analysis/report versions readable and makes no implicit
  model request (R5, R12).
- [x] **AC21** Saving a first-stage prompt edit does not requeue completed historical
  sources. New executions use the saved version, in-flight executions retain
  their snapshot, and an explicit user-selected historical rerun creates a new
  version without overwriting previous output (R10, R12).
- [x] **AC22** Changing only the stage-two Shenzhen Longtian criteria can produce a new
  topic result while reusing unchanged stage-one text, without reacquiring or
  uploading media (R3, R10, R12).
- [x] **AC23** Representative text/image/video cases preserve explicit geographic
  clues/excerpts and ambiguity through the saved stage-one output. The text-only
  topic stage distinguishes supported Shenzhen Longtian references, other
  same-name locations and insufficient evidence without fabricating certainty
  (R11, R13). Mock checks do not establish real-model quality.
- [x] **AC24** A single explicit initial-analysis action targets all never-initially-
  analysed records across pages/runs, including historical records. A set larger
  than 100 is not silently truncated or converted into repeated user selections;
  bounded execution saves each successful stage-one result independently before
  the automatic report stage consumes it. Automatic reporting never requires
  those records to be acquired or initially analysed again (R2, R3, R9, R14).
- [x] **AC25** The one-click action does not duplicate automatic queued/running work,
  redo completed records after a prompt edit, or silently retry failed/interrupted
  attempts. Repeated clicks cannot concurrently analyse the same record twice;
  separate explicit retry/reanalysis retains prior results and reasons
  (R2, R6, R12, R14).

- [x] **AC26** For a frozen task of ten records, eight successful initial analyses
  and two failures lead to one automatic report using the eight successful
  outputs after all ten have been attempted. No report is rebuilt after each
  item; later arrivals do not extend the task or change its report snapshot
  (R2, R3, R4, R14).
- [x] **AC27** More than 100 successful initial analyses are all admitted to
  text-only topic evaluation. Internally bounded requests produce one logical
  report with inspectable relevant evidence and truthful coverage, without
  silent truncation, a mandatory second click, or manual scope narrowing.
  Size/provider failures remain visible and do not redo stage one (R3, R6, R11, R14).
- [x] **AC28** Legacy report versions remain readable and identified as legacy.
  Their scope-specific judgments are not silently certified as new generic
  initial analyses or automatically rerun during upgrade; explicit reanalysis
  preserves the legacy version (R5, R12, R13).

## Out of Scope

- A named prompt-template library or per-collection-task prompt assignments are
  explicitly deferred from the first version; the approved scope is two shared
  editable defaults and stage-two per-request overrides.
- New platform adapters, crawler repair, model-provider configuration changes,
  notification/delivery workflows, or splitting the application into separately
  deployed services. These are not implied by the approved direction.
- New paid provider calls or browser collection against real accounts during
  planning. Live validation will require separately scoped authorization.


## Delivery Ownership

This task owns the requirements, cross-deliverable acceptance and final review.
The following child tasks were approved in dependency order. A, B and C have
passed implementation, full-scope checks and isolated browser acceptance. Parent
AC01–AC28 evidence is recorded in `research/acceptance-matrix.md`, including the
live-model limitations and observed response-recovery boundary. None is
committed, archived or deployed to production.

| Order | Child task | Deliverable and requirement ownership |
| --- | --- | --- |
| A | `08-29-shared-results-initial-analysis` | Shared results, two prompt defaults, reusable stage-one evidence, bulk/automatic admission, legacy preservation and independent recovery: R1, R2, R4–R6, R9, R10, R12–R14. |
| B, after A | `08-29-scheduled-rule-collection` | Rule-referenced scheduling, busy/offline policy and collection-to-analysis handoff: R1, R7, R8; integrates R2. |
| C, after A and B | `08-29-automatic-text-reports` | Automatic frozen-input text reports, relevance, capacity, overrides, historical views and full integration: R3–R6, R9–R14. |

These are implementation slices, not separately enabled partial product releases.
A owns the stage-one parts of shared acceptance; C owns the report parts and
end-to-end AC03–AC09, AC16–AC28. B owns AC10–AC12 and scheduling integration
in AC13. The parent verifies every AC01–AC28 before feature release.

## Constraints and Planning Review

- Preserve existing overview plus source-cited prose; prompts control focus,
  not a mandatory risk score, incident taxonomy or new export format.
- Individual acquisition/model requests remain bounded. Capacity is handled
  inside the report implementation, not by capping the user's bulk selection.
  More sources can mean more text requests, longer waits and greater provider
  usage. No unlimited model-context or real-quality claim is made.
- No automatic historical backfill, prompt-edit rerun or failed-attempt retry.
  Initial enablement and provider changes must make the automatic media/model
  boundary explicit. Migration, reads and planning do not authorize paid work.
- Architecture, schema, migration, state machines and bounded aggregation are
  proposed in `design.md`; ordered execution, checks and rollback gates are in
  `implement.md`. Research is retained under `research/`.
- No blocking product question remains after the confirmed report timing.
  Technical defaults and operational safeguards are included in this final
  plan for review, not attributed to separate user approvals.
- The PRD convergence pass retains R1–R14, the original 25 acceptance mappings,
  source anchors and superseded-decision boundaries; AC26–AC28 make timing,
  capacity and legacy safety explicit.
- The final planning summary received subsequent explicit approval (“开始吧。”)
  on 2026-08-29. A/B/C and final parent implementation acceptance have passed;
  `research/implementation-status.md` records actual execution and cleanup.
  Task metadata remains unarchived pending the commit/bookkeeping workflow.
  Live account/model work, production migration, commit and feature activation
  remain separate gates; implementation approval does not authorize them.
