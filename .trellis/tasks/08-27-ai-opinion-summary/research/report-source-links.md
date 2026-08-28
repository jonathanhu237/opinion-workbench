# Report source hyperlinks — approved follow-up

The user requested recognizable hyperlinks attached to the report on 2026-08-28.
This is a small presentation follow-up within the active summary task, not a
new analysis/generation operation.

## Current gap and owner

`frontend/src/routes/collection-ai-summary.tsx` already resolves each paragraph's
`source_ids` to frozen sources and renders a separate full-title `SourceLink`
under it. Make the citation directly recognizable as a compact hyperlink in the
report paragraph, rather than another long source-title block. Preserve the
existing source resolution and XHS action behavior.

## Boundary

- Implementation owns `frontend/src/routes/collection-ai-summary.tsx` and its
  adjacent `.test.tsx`; use existing platform presenters, `buttonVariants` and
  Shadcn Button. Keep existing theme, navigation, dependencies and analysis rows.
- Attach concise underlined citations to their report paragraphs, with platform
  names and a distinguishable source label/accessible name when multiple sources
  are cited. All citations remain visible without expanding content analyses.
- For the four ordinary platforms use semantic anchors targeting the saved
  `content_url`, opening a new tab with safe rel attributes. XHS keeps a
  link-styled button using the existing backend-mediated stored-result action,
  pending/disabled/feedback behavior; do not fabricate a signed link.
- Resolve IDs only through validated frozen source records, not current result
  pagination or LLM prose. Model HTML/Markdown remains escaped text.
- No backend/schema/model/prompt changes, export feature, source acquisition,
  generation, saved-report mutation, paid request, or credential inspection.
- Main owns this task's documentation/spec updates and real local-page smoke
  check. Do not modify prior uncommitted Douyin repair work.

## Checks

Show correct saved hrefs and source labels inside the appropriate paragraph;
exercise multiple/repeated citations, keyboard access, new-tab rel, escaped
model text, invalid citation suppression and unchanged XHS pending/error path.
Run focused tests and frozen frontend install/format/lint/type/test/build gates
in an isolated Centaurus source checkout after one-way rsync. No runtime,
database, credentials or media are transferred. Main verifies the saved summary
6 in the local application without generating another version or calling a model.

## Observed baseline

Main inspected the actual saved summary 6 in the in-app browser before this
change. Its citation was already an anchor to the stored Douyin video, with
`target="_blank"`, `rel="noreferrer"`, a separate `DIV` parent and computed
`text-decoration-line: none`. The gap is discoverability and paragraph placement,
not missing persisted source references. The page console had no errors/warnings.
The saved operation remained completed with finish time
`2026-08-28T10:27:15.752526Z`, **2 requests / 13,518 tokens**.

## Implemented behavior and verification

The two-file change extends the existing `SourceLink` with an optional citation
number. Report paragraphs render `原文 N · 平台` using the frozen item's
`position + 1`, with the complete stored title in its accessible name and title
attribute. Repeated references retain that number. Citations are persistently
underlined; ordinary sources use their stored href with `_blank` and
`noopener noreferrer`, while XHS remains the existing link-styled action.
Default analysis-row links are unchanged.

Implementer source hashes:

- Component: `15723b9cad829df28d1ed7e274badb33ab0cd97c7f2f604f3de8d33ed95203d5`.
- Tests: `9064a70435764d9780cc7047a5ffd00074bbb2bac32f1d9c34378e80453c5977`.

The implementer passed focused **26/26** tests and all frozen frontend gates on
Centaurus: frozen install, format, lint (**70 files**, no warnings/errors),
typecheck, full **288 tests / 14 files**, and production build. Node 24.20.0 and
pnpm 11.14.0 were supplied through mise. Local/remote hashes matched. Independent
review also passed frozen install, format, lint, typecheck, **288 tests / 14 files**
(including all 26 focused cases) and build against the same source hashes, with
no blocking findings or product fixes. Its full record is
`report-source-links-check.md`.

Main checked saved summary 6 in the local application after hot reload. The
visible citation is `原文 1 · 抖音`, its parent is the report `P`, its underline is
present without hover, and its href exactly matches the saved Douyin video URL.
The actual default report width was **380 CSS px** with equal client/scroll
width, and the screenshot showed the citation fitting at the paragraph end.
The link can receive visible focus; full Tab order remains covered by automated
behavior tests, not claimed from the live keyboard check. No viewport override
was applied, no external source was opened, and the page console had zero
errors/warnings. The collapsed analysis disclosure remains available below it.

After the UI checks, the saved summary ID, completed status, finish timestamp,
**2 requests / 13,518 tokens** were unchanged. No report regeneration, model
request, source acquisition, credential inspection, backend restart, runtime
write, commit, push or archive was part of this presentation change. Live XHS
opening was not exercised; its preserved interaction is covered by fixtures.
