# Current two-stage prompt system

## Existing product behavior

- The backend already owns fixed business defaults as `DEFAULT_INITIAL_INSTRUCTIONS` and
  `DEFAULT_REPORT_INSTRUCTIONS` in `backend/src/longtian_api/schemas/analysis_settings.py:16`.
  SQLite v12 seeded immutable prompt-version rows from those constants.
- The Results page currently exposes mutable global prompt editors in
  `frontend/src/routes/results-settings.tsx:74` and sends version-fenced PUT requests. This is the
  product behavior being retired, not historical prompt-version storage.
- Manual initial-analysis admission currently sends both current prompt version IDs from
  `frontend/src/routes/results.tsx:153`; its confirmation discloses both prompts even though the
  action performs only initial understanding (`frontend/src/routes/results-confirmation.tsx:83`).
- Manual reports already support one-off report instructions through `instructions_override` in
  `frontend/src/routes/results-report-actions.tsx:287` and persist the exact override without
  changing the shared prompt.
- Automatic run admission currently reads the mutable shared prompt IDs, freezes those IDs, and
  separately freezes `analysis_goal` (`backend/src/longtian_api/services/automation_workflows.py:1140`).
  The analysis child consumes the initial prompt ID; the report child uses `analysis_goal` as exact
  instructions.

## Compatibility and reuse constraints

- Content-understanding cache identity already includes the initial prompt content hash, schema,
  provider revision/endpoint/model, input version and extractor
  (`backend/src/longtian_api/repositories/content_analyses.py:552`). Custom initial prompts therefore
  must resolve to immutable prompt versions before admission; reuse is safe only when the effective
  prompt hash also matches.
- Manual and workflow analysis repositories currently require request prompt IDs to equal the
  mutable `analysis_settings` pointers (`backend/src/longtian_api/repositories/content_analyses.py:295`).
  This current-global compare-and-swap must be replaced by strict default/custom resolution inside
  the admission transaction.
- Topic-report create similarly fences against the mutable global report pointer before applying a
  one-off override (`backend/src/longtian_api/repositories/topic_reports.py:744`). With an immutable
  built-in default, replay must instead bind the complete default/custom choice.
- Historical jobs, attempts, reports and automation snapshots reference immutable prompt versions
  or embed exact report instructions. They must remain readable without rewriting their evidence.
- Existing automatic tasks may have run under a user-edited global initial prompt. Migration must
  preserve that current effective behavior as a task custom choice when it differs from the
  built-in default. Existing `analysis_goal` becomes the task's custom second-stage instructions.

## Product decisions from the current brainstorm

- Both automatic and manual flows use the same product model: choose a fixed built-in default or
  customize a copy for the current task/current submission.
- Built-in defaults are not runtime settings. A future code change to a built-in template is an
  explicit versioned product migration, never a silent settings update.
- Automatic tasks persist both stage choices. Manual initial analysis chooses only the first-stage
  prompt; manual report creation chooses the second-stage prompt at that later action.
- User-editable text is business instruction only. Application-owned safety, evidence, privacy,
  citation and strict-output contracts stay hidden and non-overridable.

