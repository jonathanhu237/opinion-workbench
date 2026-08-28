# Report Readiness, Coverage and Capacity

Read-only inspection on 2026-08-28 against `00e6973`. The user has approved the
two shared prompt defaults and per-report stage-two overrides. The latest user
request is one-click analysis of all unanalysed items. The user explicitly
clarified its target as stage one: understand each record first,
then independently aggregate those saved analyses into a report. The latest
clarification makes reports automatic: use completed initial analyses without
a separate generation click. No implementation or live work is authorized.

## Existing Evidence

- `backend/src/longtian_api/repositories/ai_summaries.py:223` rejects an active
  source and at `:229`/`:231` rejects zero or more than 100 collected sources.
  This count is the whole frozen source scope, not only relevant evidence or a
  visible page. It belongs to the old single-run summary admission.
- `backend/src/longtian_api/services/ai_summaries.py:192` uses only relevant
  completed item evidence for composition. At `:196`, no relevant evidence
  produces a bounded empty outcome explaining that unfinished/uncertain items
  remain; it does not make an extra composition request.
- `backend/src/longtian_api/services/ai_summaries.py:218` passes application-owned
  outcome counts into the final text prompt. These distinguish relevant,
  irrelevant, uncertain, incomplete and technical failures; they are content
  counts, not real-world event counts.
- `backend/src/longtian_api/services/ai_analysis.py:292` checks 1–100 unique
  evidence sources; `:300` validates count balance and relevant membership.
  At `:322`, the full system plus serialized user text must fit 120,000
  characters. This is not a guarantee that every set of 100 items fits, and
  it is not a token/context-window claim about an external model.
- `backend/tests/test_ai_analysis.py:419` verifies saved text plus coverage;
  `:450` checks the exact character boundary without trimming or splitting.
  `backend/tests/test_ai_summaries.py:95` preserves incomplete/uncertain/failed
  distinctions; `:338` preserves item analyses when composition input exceeds
  its bound. These tests were inspected, not run in this planning turn.
- `frontend/src/routes/collection-ai-summary.tsx:364` explains the 100-source
  limit; `:591` displays outcome counts; `:653` renders an overview and cited
  analysis entries. The new module must not imply coverage merely by reusing
  this old single-run status/count component.
- `backend/src/longtian_api/schemas/ai_summaries.py:179` defines a `SummaryItem`
  with `summary_run_id`, processing status and relevance decision. This is an
  item inside one old combined operation, not independent global status for
  each new AI stage. `backend/src/longtian_api/database.py:150` stores that
  ownership, with uniqueness per summary/content at `:168`.
- `backend/src/longtian_api/repositories/ai_summaries.py:399` finds compatible
  completed cached evidence for an already-admitted item. A cache miss is not
  proof of never having been analysed. The approved forward-only prompt policy
  still prevents a bulk eligibility query from accidentally reprocessing the
  whole library after a prompt edit.
- `backend/src/longtian_api/services/ai_summaries.py:181` processes old combined-
  operation items serially, then enters composition at `:188`. This is evidence
  for the current once-after-items cadence, not the new user-owned cadence
  decision. Do not copy its report-owned item lifecycle back into the decoupled
  initial-analysis store merely because automatic handoff is now requested.

## Earlier Recommendation and Superseding Decision

The assistant proposed user-confirmed partial reports and retaining a 100-source
report scope with manual time-window narrowing for large inputs. The user first
clarified the stage-one bulk action, then explicitly required automatic reports
using completed initial analyses. This settles using ready material and removes
the separate generation click/partial-generation confirmation prerequisite.
The 100-source report capacity proposal was never accepted and is superseded
by the bounded multi-request proposal in `../design.md`. Do not cap initial
analysis or silently truncate an automatic report based on the old proposal.

## Confirmed Two-Stage Model and One-click Action

- The user explicitly defines stage one as understanding what each record is
  about and stage two as aggregating those analyses into a report. One-click
  analysis targets records that have not undergone stage one. The earlier
  assistant interpretation as a stage-two action is incorrect and superseded.
- Persist initial analysis and report generation as separate operations, but
  automatically hand completed initial analyses to reporting without a second
  click. Initial analysis saves reusable per-record text from raw content/media;
  report generation only reads that saved text. Shenzhen Longtian/topic filtering
  remains within the report's user instructions, not a third user-facing stage.
- The bulk initial-analysis action selects all eligible never-initially-analysed
  records across pages/runs, including historical records. It is an explicit
  user selection of history, consistent with the earlier no-automatic-backfill
  policy. It does not revoke automatic new-result processing.
- Share admission with the automatic queue: queued/running work cannot be
  duplicated, completed output cannot be requeued after a prompt edit, and
  failed/incomplete/interrupted work retains its separate explicit retry path.
  These states must not be collapsed into one "not completed" selection.
- Freeze the admitted initial-analysis set and first-stage prompt/configuration,
  execute bounded work with visible per-record progress, and save each outcome.
  The old report's 100-source cap does not bound this bulk selection; individual
  media/model size and ownership checks remain required. Committed successful
  output becomes input for the separate automatic report stage after the task
  settles. Report failure cannot roll back initial-analysis success.
- Existing first-entry-time semantics remain applicable to independently chosen
  report scopes. One initial analysis can serve multiple reports; report
  membership must not be a destructive or universal "already reported" flag.

## Confirmed Automatic Readiness and Report Cycle

The user explicitly wants automatic report generation from however many initial
analyses are complete. No report button or separate approval of partial readiness
is required. Preserve counts/reasons for unprepared/failed records; none can be
treated as analysed or unrelated. Reporting must not acquire media, start stage
one or retry it, and it cannot claim complete coverage of unanalysed sources.

On 2026-08-29 the user approved one automatic report when every record in the
current initial-analysis task has been attempted, using that task's successful
saved output and exposing the remainder. In the example, eight successes and
two failures lead to a report from the eight successes without another click.
There is no all-success gate, per-item report rebuilding or cumulative
all-history scope. Later arrivals must not prolong the admitted task. This is
a product decision, not approval to implement or make live model requests.

The proposed capacity design uses per-source text judgments, bounded relevant
sections and a bounded overview tree, retaining all sections in one logical
report. Every call checks the exact serialized prompt/input size and output
schema; a single oversized input fails visibly. No first-100 truncation, required
manual narrowing, unlimited context or automatic multi-report splitting.
See `../design.md` section 5 for call counts, usage, failure and citation contracts.

## Technical Design Follow-up

- Keep valid incomplete coverage separate from provider/validation failures and
  record any stage-two failures truthfully; explicit retry and no hidden repair
  calls continue to apply. Prompt edits cannot override the source/citation
  contract or make missing input complete.
- Specify a durable/idempotent automatic admission signal and frozen readiness,
  source, prompt and configuration snapshots. Do not switch an admitted report's
  source set midway; new evidence belongs to a later report/version. Keep source
  provenance, known-input-change protections and independent failure/retry state.
- Preserve overview plus cited prose as the compatible report presentation;
  user prompts control focus within the validated output contract. No new
  mandatory risk taxonomy, event counts or export format is implied.
- Choose evidence-preserving stage-one bounds and text-only stage-two call
  strategy in design. Account for custom instructions in every size check;
  bounded batches/aggregation must not hide dropped sources or bypass request
  limits. An oversized individual input remains a visible failure, not a reason
  to reacquire media from a stage-two operation or silently truncate evidence.

No product code, scheduler, database migration, browser action, model request or
test/build workload was run for this research.
