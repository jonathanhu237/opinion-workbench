# Verification — Plain-Language UI Copy

## Outcome

- Reviewed the shared shell and every product route group in the task scope.
- Updated 36 frontend source/test files; the change is copy and conditional rendering only.
- Removed the initiating workbench sentence without replacing it with another lifecycle
  explanation.
- Removed other helper text that repeated visible headings or idle states, including the duplicate
  automatic-run error announcement.
- Kept concise warnings for model/API usage, collection, scheduling, destructive actions,
  incomplete evidence, uncertainty, and explicit retry.
- Did not change backend code, API requests, storage, task state, polling, retry behavior, or model
  prompts.

## Source Audit

The final product-source search (excluding tests and fixtures) returned no occurrences of:

`同一归属`, `健康状态`, `投影`, `运行快照`, `已保存产物`, `冻结范围`, `冻结意图`,
`报告合成`, `固定工作流`, or `文字判断`.

The frontend's exact API error-message contracts were intentionally preserved. A plain-language
presentation must happen after strict response validation; changing only the expected wire message
would turn valid backend errors into `invalid_response`. This guardrail is recorded in
`.trellis/spec/frontend/type-safety.md`.

## Automated Gates

Run from `frontend/` with mise Node 24:

- `pnpm install --frozen-lockfile` — passed; lockfile already current.
- `pnpm format:check` — passed.
- `pnpm lint` — passed.
- `pnpm typecheck` — passed.
- `pnpm test:run` — passed: 25 files, 503 tests.
- `pnpm build` — passed: 2,361 modules transformed.

Repository checks:

- `git diff --check` — passed.
- `python3 ./.trellis/scripts/task.py validate 09-01-plain-language-ui-copy` — passed; both context
  files contain six valid entries.

## Browser QA

Existing local services were used without submitting forms or starting platform/model work:

- API: `http://127.0.0.1:8000` (`/api/v1/health` returned `status=ok`).
- Frontend: `http://127.0.0.1:5174` (HTTP 200).

Read-only checks covered:

- `/`
- `/automation-runs/2`
- `/results?report=1`

Each page was checked at 1440×900 and 390×844. All six page/viewport combinations had no
horizontal overflow, and browser console warning/error logs were empty. The workbench no longer
shows explanatory text below idle stage labels. The automatic-run page shows one actionable top
error (`这一步没有完成。可从“初步分析”重试。`) and keeps the stage-specific failure in context.

No page control was activated during browser QA, and the temporary browser tab and viewport
override were closed/reset afterward.
