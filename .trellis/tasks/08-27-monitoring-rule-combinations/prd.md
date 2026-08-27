# 监控对象与舆情关键词组合

## Goal

Let the user maintain `监控对象` and optional `舆情关键词` separately in the existing rule editor, inspect generated full queries, and reuse existing single-/multi-platform collection without hand-writing every combination. This child owns parent R5, R10 and R13, not media acquisition or AI summary.

## Background and Decisions

- The user accepted two input areas and generated-query preview, then explicitly accepted leaving issue keywords empty. Empty means search the objects as entered; populated means combine each object with each issue.
- Current rules are flat ordered phrases. The editor splits on newlines, not spaces (`frontend/src/routes/monitoring-rules.tsx:60`), and the backend preserves trimmed display text (`backend/src/longtian_api/services/monitoring_rules.py:154`). Never infer a split of old phrases.
- Existing rules allow 100 terms, but execution accepts at most 20 per platform (`backend/src/longtian_api/services/search_runs.py:47`; `backend/src/longtian_api/services/search_batches.py:170`). Preserve those boundaries with visible effective counts.
- Collectors snapshot `rule.terms`; batch children consume the batch snapshot. The enabled toggle sends a full replacement and must preserve both groups (`frontend/src/routes/monitoring-rules.tsx:357`).

## Requirements

- **Q1 — Two simple inputs.** Retain rule name, enable/disable, edit and delete. Add a required monitoring-object list and an optional issue-keyword list, one entry per line. Reuse current shadcn form/dialog primitives and theme; no new page or Boolean editor.
- **Q2 — Predictable combinations.** When issues exist, generate object-plus-issue phrases in object-major/input order with one separating space. Otherwise use object phrases unchanged. Preview full queries and their count before saving. This is query composition, not guaranteed strict AND matching by platforms.
- **Q3 — Preserve editable groups.** Save/reload both lists without flattening them irreversibly. Edit/toggle/delete must preserve unrelated data; writes are atomic and backend validation is authoritative.
- **Q4 — Existing bounds remain.** Preserve name/phrase lengths, normalized duplicate rejection, the 100-effective-query rule cap and the 20-query-per-platform execution cap. Warn above 20 and direct the user to split rules; do not silently truncate or launch extra runs. Normalized generated-query collisions are validation errors, not silently removed entries.
- **Q5 — Lossless old data.** Old complete phrases become monitoring-object entries with empty issues. Preserve rule IDs, names, enabled flags, order, one-time seed/deletion behavior and all historical run/batch snapshots. Do not guess phrase boundaries.
- **Q6 — No execution side effects.** Opening/editing/previewing/saving rules makes no browser/crawler/media/AI request. Existing explicit collection uses the generated terms and preserves platform selection, limits, snapshots, deduplication and source-opening behavior.

## Acceptance Criteria

- [x] Two objects and two issues preview/save four expected phrases in stable order; both lists survive reload/edit (Q1–Q3).
- [x] Empty/blank issue textarea saves as an empty list and yields unchanged objects, including internal spaces (Q2, Q5).
- [x] Migration/repeated initialization preserve old queries, rule IDs, enabled states and history without recreating deleted defaults (Q5).
- [x] Toggle/full replacement retain both groups; failures roll back atomically (Q3).
- [x] Blank/duplicate/long values and generated collisions fail clearly. 20 queries are executable; 21–100 remain saveable with an execution warning; over 100 cannot save. No silent truncation (Q4).
- [x] Single-platform/batch fixtures receive compiled terms; edits after batch creation cannot rewrite child/history scope or deduplication (Q5, Q6).
- [x] Existing shadcn/theme, labeled errors, keyboard access and narrow-screen layout remain intact; CRUD/preview tests prove zero crawler/media/model calls and full Centaurus gates pass (Q1, Q6).

## Out of Scope

- Arbitrary AND/OR nesting, guaranteed literal result matching, keyword suggestions/dictionary, AI screening, media acquisition or summary.
- Raising limits, automatic query splitting, scheduling, new platforms, provider calls, rewriting history, resetting user data, changing AI configuration or redesigning the application.

## Artifact Status

- Two-input/preview/empty-list decisions are resolved; design, execution checklist and curated context accompany final review.
- The user approved the final child summary with `ok` on 2026-08-27. Implementation is authorized for Q1–Q6 only; existing uncommitted AI-configuration work must be preserved. No commit, push, media acquisition or model calls are authorized by this approval.
- Implemented and independently checked on 2026-08-27. Full Centaurus gates: backend 353 tests, frontend 164 tests, format/lint/typecheck/build passed. Main-session isolated UI checks passed; see `verification.md` and `research/check-review.md`. Code remains uncommitted; no user database migration/restart or child-scope expansion occurred.
