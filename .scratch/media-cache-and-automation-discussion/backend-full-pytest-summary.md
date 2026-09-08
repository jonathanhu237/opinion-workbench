# Backend full test attempt

- Command: `uv run pytest -q`
- Working directory: `backend/`
- The first raw run and the post-fix run both stopped around 23% while old
  media-dependent tests were running or while pytest cleaned large temporary
  media trees. No fourth full run was started.
- Final post-fix attempt: `uv run pytest -q --basetemp=/tmp/longtian-backend-full-pytest`
- Final process: PID 30481, corresponding to session 11695. It stopped growing
  for about eight minutes; `lsof` showed a temporary
  `test_reuse_tracks_known_versio0/summary.sqlite3` while the suite was idle.
  One SIGINT was sent as requested. The final log reports **315 passed, 31
  failed, interrupted after 558.94s**; the session did not reach a clean
  completion because it was interrupted after the hang.
- Raw logs were moved to the ignored directory
  `runtime/tool-validation/media-exit-automation/`:
  - `backend-full-pytest.log` — first raw attempt, interrupted during pytest
    traceback/cleanup.
  - `backend-full-pytest-fixed.log` — post-tick-fix attempt, interrupted in
    pytest temporary-directory cleanup.
  - `backend-full-pytest-final.log` — final partial summary above.

## Failure grouping

The 31 reported failures are old media-pipeline expectations exposed by the
text-only/media-exit change, plus one migration expectation. They are retained
in the raw log for review and were not hidden by changing pytest collection.

- `tests/test_ai_analysis.py`: 11 failures expecting image/video/audio model
  inputs or media validation.
- `tests/test_ai_summaries.py`: 9 failures expecting media staging or the old
  media-backed worker lifecycle.
- `tests/test_ai_summary_repository.py`: 4 failures coupled to the old media
  staging lifecycle.
- `tests/test_best_effort_enrichment.py`: 2 failures using old media staging.
- `tests/test_collection_schedule_repository.py`: 1 failure expecting the old
  `media_cache_policy` table.
- `tests/test_collection_schedules.py`: 1 failure using the old media-backed
  analysis handoff.
- `tests/test_content_analyses.py`: 3 failures using the old media-backed
  analysis lifecycle.

The focused replacement coverage passes: `tests/test_media_exit.py` is 6
passed, including mixed-entry upgrade, unlink failure retry, and directory
scan failure retry. The focused automation tick regression also passes.
