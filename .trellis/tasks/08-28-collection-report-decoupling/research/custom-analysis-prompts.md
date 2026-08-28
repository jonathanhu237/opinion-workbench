# Reusable Content Summaries and Text-only Topic Analysis

Planning research on 2026-08-28, against local commit `00e6973`. This records the
latest user clarification, not implementation approval or model-quality proof.

## User Direction

Continue discussing the current Trellis task. The product responsibilities are:

1. Monitoring rules remain rules, defining collection/search criteria.
2. The collection module lets a periodic task reference a chosen rule and writes
   collected data into results.
3. In the latest clarification, Results and Analysis first summarises/analyses
   all new results into saved text. The next stage uses that text to identify
   sources genuinely concerning Shenzhen Longtian and produce topic analysis
   and a report only for the relevant subset. Prior unsatisfactory output
   motivates user control of the criteria, not an unproven claim about its cause.

This order supersedes the assistant's earlier relevance-first/deeper-analysis
proposal. The user's two stages are content understanding for all new sources,
then reusable text-based topic analysis/reporting. Custom topic instructions
remain requested. Stage one runs automatically after collection. Stage two was
initially agreed as on demand, but the latest user clarification supersedes that:
reports must be generated automatically from completed initial analyses, with
no separate generation click. Both stages' prompts remain editable. This is a
planning decision, not a live-execution authorization.
The user then approved forward-only prompt changes: later executions use the
saved version, while in-flight/historical work keeps its original version.
Historical reruns must be explicitly selected; no automatic full-library rerun.
The next accepted decision is report selection by a first-entry-time window
across collection runs, not by original publication time or last re-observation.
The user subsequently approved persistent pending work for newly collected
content, manual selection of pre-existing unanalysed history, and explicit
retry of failed/interrupted analysis. Neither collection's repeated marker nor
a prompt edit makes historical content newly eligible for automatic paid work.
The user also approved two editable shared defaults, with a stage-two per-report
override and a separate explicit save to change its default. The first version
does not include named templates or per-collection-task prompt assignments.

The assistant's earlier single-rule-per-report limit was never approved. A
collection rule remains provenance/filter data; it must not replace the user's
separately chosen analysis objective.

## Existing Code

- `backend/src/longtian_api/services/ai_analysis.py:102`: `AnalysisContext` only
  contains `rule_name` and query `terms`.
- `backend/src/longtian_api/services/ai_analysis.py:167`: `_ANALYSIS_PROMPT` and
  `_SUMMARY_PROMPT` are fixed constants, used directly as system instructions at
  `:263`. The existing system prompt explicitly treats monitoring-rule strings
  as material, not editable instructions. Adding custom prompts requires an
  intentional instruction boundary, not placing them into query terms/snippets.
- `backend/src/longtian_api/services/ai_analysis.py:115`: every successful item
  currently contains a decision, reason and evidence summary, including
  irrelevant/uncertain verdicts. This is still a scope-specific judgment, not a
  neutral reusable content-understanding record. The implementation must not
  simply relabel historical scope-specific summaries as generic new-stage
  summaries without establishing that they contain the required evidence.
- `backend/src/longtian_api/services/ai_summaries.py:192`: final composition
  already excludes all but relevant item evidence. Preserve that invariant,
  while distinguishing it from the new all-result content-understanding stage.
- `backend/src/longtian_api/schemas/ai_settings.py:32` and
  `frontend/src/lib/api/ai-settings.ts:9`: existing model settings do not expose
  prompt fields. Keep provider credentials separate from business instructions.
- `backend/src/longtian_api/schemas/ai_settings.py:40` exposes the provider's
  model/endpoint/key-presence/revision projection. Its revision is not a custom
  instruction version. A shared prompt-default design is a product choice,
  not a consequence of this existing shared provider configuration.
- `backend/src/longtian_api/repositories/ai_summaries.py:311`: reuse incorporates
  a code-owned prompt version and historical rule context. An editable prompt's
  exact snapshot/version must become part of the relevant compatibility check.
- `backend/tests/test_ai_analysis.py:311` and `:372`: existing tests distinguish
  legitimate uncertain/irrelevant decisions from schema/input failures. Prompt
  customization must not collapse those distinctions.

## Design Constraints

Resolved technical choices are now specified in `../design.md`; the constraints
below remain the evidence base, not unanswered product questions.

- User-authored stage-one instructions control content understanding and summary
  focus; user-authored stage-two instructions control topic relevance and reporting.
  Collected platform text/media remain untrusted data, not instructions. Keep
  app-owned structured output/state validation, citation identity, usage
  accounting and credential protections intact. Do not expose the entire
  transport/output contract as an unrestricted editable system prompt.
- Store immutable instruction snapshots on analyses, not only a pointer to a
  mutable "latest prompt". Prompt changes must not mutate a running operation,
  make incompatible old judgments look fresh, or trigger automatic paid work.
- Automatic eligibility and prompt-cache compatibility are different concepts.
  Existing `find_cached` matches a cache key for an explicitly admitted request
  (`backend/src/longtian_api/repositories/ai_summaries.py:399`); it is not an
  automatic backlog enumerator. With editable first-stage prompts, selecting
  every source lacking a result for the newest prompt would silently requeue
  the entire historical library after an edit. Do not inherit that behavior
  merely by reusing cache invalidation logic in the new automatic runner.
- Content-extraction and topic-report instructions have different dependencies.
  A stage-two geography/topic prompt change must not invalidate otherwise
  compatible stage-one textual evidence. A changed source/first-stage prompt or
  required extraction schema may require new stage-one understanding. Neither
  change rewrites earlier report snapshots or silently triggers paid work.
- Preserve raw collected results when excluded. A relevant-only view or report
  is not deletion of unrelated data. Unknown geography or incomplete media is
  not proof of irrelevance.
- All new sources receive content understanding before topic filtering, even
  those later excluded. Stage two must consume the saved textual material only;
  no second media upload or hidden media reacquisition. Text-only topic work
  still has model cost. Do not insert a relevance/title-only prefilter before
  stage one, since that contradicts the revised user order.
- Custom instructions can improve control of the target and output; they do not
  repair missing material or prove geographic truth/model accuracy. Offline
  contract tests and separately authorized representative media acceptance
  remain different quality gates.
- The existing overview plus source-cited text entries can remain the compatible
  report presentation, with substantive focus controlled by user instructions.
  The location example does not authorize adding mandatory risk scoring,
  sentiment classification, case assignment, verified-incident claims or a new
  taxonomy automatically.

## Text Evidence Fidelity

The current `evidence_summary` has a 1,000-character bound and is tied to a
particular monitoring scope (`backend/src/longtian_api/services/ai_analysis.py:115`).
Current composition also receives saved source title/body
(`backend/src/longtian_api/services/ai_summaries.py:209`), so do not reduce the new
text boundary to one short abstract and lose evidence.

The stage-one schema/prompt should preserve, with clear source attribution:

- a content summary and key factual claims, not a Shenzhen-only relevance verdict;
- explicit location clues and brief supporting source excerpts, including
  visible/heard clues from image/video/audio when present;
- time context and whether it is explicit, relative or unknown;
- useful media observations and uncertainty/coverage limitations;
- stored source identity and links resolved by the application.

Do not infer an exact place merely from a same-name keyword, uploader identity,
or an unrelated location label. A summary is still model-generated evidence,
not verified geographic truth. Stage two should retain an unknown category when
the text cannot support the requested match. Filling missing clues by silently
reopening media would violate the requested text-only second-stage boundary.

Keeping useful source text/excerpts is an accuracy trade-off against text size.
Choose bounds and overflow behavior in the design; do not silently truncate.
The existing media-retention policy need not change merely to enable repeat
topic reports, because those reports consume saved text rather than media.

## Confirmed Decisions

Automatic first-stage summaries, automatic second-stage reports, editable
instructions for both, and forward-only prompt changes with user-selected
historical reruns are now confirmed, as is first-entry-time report selection
across collection runs. Do not re-ask those decisions. Mixed-version
history is allowed; each operation/result retains its actual prompt snapshot.

The initial schedule/missed-occurrence policy is now approved and documented
in `scheduling-boundaries.md`. Pending-analysis persistence and historical
backfill are also resolved: new-content work remains visible across runs;
historical analysis and failed/interrupted retries require explicit selection.
Do not automatically sweep the historical library or reinterpret a cache miss
as permission to do so.

The user has approved this prompt configuration and reuse policy:

- Two separately editable shared defaults owned by Results and Analysis, not
  embedded in a monitoring rule or provider credentials.
- Stage one automatically uses the saved content-understanding default, with
  the already-approved immutable snapshot and forward-only edit semantics.
- Stage two starts each request from its saved topic-analysis/report default;
  the user can change only that request's text. A separate explicit save is
  needed to change the shared default. A one-off report must not silently modify
  subsequent reports or stage-one instructions.
- Defer named template libraries and per-collection-task prompt assignments.

This supports reusable common content evidence and one-off report topics, at
the accepted cost of not assigning different automatic summary styles to
different collection tasks in the MVP. Approval covers planning scope, not live
execution or implementation. The provider configuration did not settle this
choice; the user did.

The user now explicitly resolves the meaning of one-click analysis: it performs
stage-one initial understanding for all records not yet initially analysed.
Stage two independently aggregates saved analyses into a report. The latest
clarification makes that aggregation automatic, using however many records have
completed initial analysis. The assistant's
prior interpretation as bulk stage-two topic analysis was incorrect and is
superseded. Topic filtering remains within the report action under the previously
approved relevant-only instructions, not a new user-facing third stage.

The first-stage bulk action uses the shared first-stage prompt, including for
never-analysed historical records explicitly selected through "all". It saves
initial analyses before the separate automatic report stage reads them, without
changing either default or turning prompt edits into implicit historical
reanalysis. Existing automatic new-result work is retained, sharing
queue ownership/idempotency; failed/interrupted attempts retain separate explicit
retry controls. This is explicit historical selection, not automatic backfill.

See `report-admission-boundaries.md` for the revised proposal and source evidence.
Bulk eligibility must remain distinct from prompt compatibility: editing a
default cannot turn all completed historical content into unanalysed content.
The user has resolved report readiness: automatically use completed initial
analyses; unprepared/failed records do not have to finish first and cannot be
invented as analysed evidence. Prompt defaults remain independent; automatic
reports use the saved stage-two default without requiring a per-report editor.
The optional one-off override must not become a mandatory generation step.

On 2026-08-29 the user approved one automatic report after every member of the
current initial-analysis task has been attempted, using its saved successes.
No per-item rebuilding or all-history accumulation is implied. The proposed
bounded text-only judgment, sections and overview strategy is in `../design.md`;
it preserves one logical report without a first-100 truncation. These technical
choices await the final planning review, not another cadence question.
