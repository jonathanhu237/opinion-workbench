# Plain-Language UI Copy

## Goal

Make the local administration UI easier to understand by removing explanations that do not help
the user decide or act, and by rewriting necessary status, error, confirmation, and evidence copy
in short, direct Chinese.

The initiating defect is the workbench sentence at
`frontend/src/routes/workbench.tsx:755`: `问题会在同一归属出现更新的健康状态后自动从这里消失。`
It exposes internal projection language instead of helping the user. The intended behavior is to
remove this sentence rather than mechanically paraphrase it.

## Background

- The application is a local React administration tool used by a non-technical operator.
- User-visible copy is spread across `frontend/src/routes/`, the application shell, and frontend
  presenter/error mappings.
- The repository has accumulated implementation terms such as `归属`, `健康状态`, `投影`,
  `冻结`, `修订`, `运行快照`, `已保存产物`, `文字判断`, and `报告合成`.
- Some explanatory paragraphs repeat an adjacent heading, status, or button and can be deleted.
- Other copy protects an important boundary: model/API cost, deletion, incomplete evidence,
  uncertainty, explicit retry, or whether an action starts collection/analysis. Those meanings
  must remain, but should be expressed plainly.
- The frontend currently has no uncommitted changes. Existing dirty backend/spec/submodule paths
  belong to other work and must not be touched.

## Requirements

### R1 — Audit the whole user-facing frontend

Review user-visible copy in:

- the workbench and application shell;
- platform accounts and monitoring rules;
- automatic task creation, history, and run detail;
- collection pages and recovery/summary dialogs;
- results, initial analysis, report history/detail/actions, and AI settings;
- frontend presenter and error mappings whose text is rendered by those pages.

Tests, fixtures, developer comments, API schema validation messages that never reach the product
UI, model prompts, generated report text, and third-party MediaCrawler copy are not product-copy
inventory.

### R2 — Delete copy that does not help

Remove helper text when it only:

- repeats the adjacent heading, badge, count, or button;
- describes internal storage, projection, ownership, snapshot, child artifact, or lifecycle
  mechanics;
- reassures the user that a simple read/refresh does not start unrelated work when the surrounding
  action is already unambiguous;
- narrates a normal automatic state transition without requiring user action.

Deletion must not remove the accessible name of a control, loading/error announcement, or the only
explanation of a consequential action.

### R3 — Rewrite necessary copy in plain Chinese

When text is necessary, it must state the visible outcome and, when applicable, the next action.
Prefer ordinary product words such as `本次任务设置`, `任务版本`, `处理结果`, `相关性判断`,
`生成报告`, `未分析`, and `请重试` over internal implementation terms. Keep sentences short and
avoid stacked clauses, double negatives, and explanations addressed to developers.

### R4 — Preserve essential truth and safety

Keep concise copy for:

- actions that can delete data, start platform collection, call a model, consume API quota, retry
  failed paid work, or enable a schedule;
- missing or partial source evidence and the difference between an uncertain result and a proven
  fact;
- errors that require login, remote-debugging approval, configuration, retry, or another concrete
  user action;
- the fact that an empty report can be a successful result when no source is sufficiently relevant.

Copy cleanup must not change task state, API requests, polling, retry behavior, saved data,
evidence classification, report semantics, or model prompts.

### R5 — Keep the interface accessible and testable

Preserve semantic headings, form labels, `aria-label`/`aria-describedby` relationships, live
regions, error placement, keyboard behavior, and visible recovery controls. Update behavior tests
to assert the new visible wording and the absence of removed internal-language copy.

## Acceptance Criteria

- [ ] **AC1 (R1):** Every product route and shared shell/presenter surface has been reviewed; the
  implementation diff covers all user-visible candidates that violate this PRD, not only the
  initiating workbench sentence.
- [ ] **AC2 (R2):** The initiating workbench detail is removed, and no equivalent explanation is
  inserted in its place.
- [ ] **AC3 (R2, R3):** Prominent visible copy no longer uses unexplained internal terms including
  `同一归属`, `健康状态`, `投影`, `运行快照`, `已保存产物`, `冻结范围`, `冻结意图`, `文字判断`,
  or `报告合成`; any semantically necessary version/scope information uses ordinary wording.
- [ ] **AC4 (R2):** Redundant helper paragraphs are removed wherever the adjacent UI already
  communicates the same status or action.
- [ ] **AC5 (R3, R4):** Retained errors and confirmations say what happened and what the user can do,
  while paid/external/destructive actions and evidence limitations still have concise warnings.
- [ ] **AC6 (R4):** Empty, partial, failed, cancelled, interrupted, and stale states retain their
  distinct meanings; the copy cleanup causes no workflow or API behavior change.
- [ ] **AC7 (R5):** Updated route tests cover representative workbench, automation, collection,
  results/report, platform, and settings states using accessible visible text.
- [ ] **AC8 (R5):** Frontend formatting, lint, type-check, full Vitest suite, and production build
  pass.
- [ ] **AC9 (R5):** Loopback browser QA covers the workbench and representative automation/report
  pages at desktop and narrow widths with no console warnings/errors or copy overflow.

## Out of Scope

- Backend/API contracts, database records, workflow logic, model behavior, prompts, and generated
  user content.
- A visual redesign, navigation change, component-library change, or new copy-management system.
- Rewriting technical identifiers inside developer-only logs, tests, comments, Trellis artifacts,
  or third-party code.
- Hiding evidence limitations, costs, destructive consequences, or actionable recovery guidance
  merely to make a page shorter.
