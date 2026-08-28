# Report source links — independent check

Date: 2026-08-28. **PASS** for the presentation-only follow-up defined in
`report-source-links.md`. No blocking finding or product correction was needed.
The reviewer changed only this report; previous media repair and other dirty
work were preserved.

## Scope and method

Read `check.jsonl`, its references, PRD/design/implement and the latest follow-up
brief. Applied `trellis-check` and the frontend quality/type/component/state
contracts. The targeted `ui-ux-pro-max` accessibility lookup reinforced checking
visible focus, semantic keyboard operation and accessible source names; it did
not introduce a redesign, new component, dependency or style system.

Only these frozen frontend files were reviewed and synchronized one-way to the
existing isolated Centaurus checkout:

| File under `frontend/src/routes/` | SHA-256 |
| --- | --- |
| `collection-ai-summary.tsx` | `15723b9cad829df28d1ed7e274badb33ab0cd97c7f2f604f3de8d33ed95203d5` |
| `collection-ai-summary.test.tsx` | `9064a70435764d9780cc7047a5ffd00074bbb2bac32f1d9c34378e80453c5977` |

These hashes matched local/remote before the gate and remained unchanged after
it. The package manifest and lockfile also matched on both sides, before and
after the frozen install. No runtime, database, media, profile or credential was
copied; no service was started or stopped by this reviewer.

## Findings

- Report citations are phrasing content inside their report `p`, persistently
  underlined and labelled `原文 N · 平台`. The full stored title remains in both
  the accessible name and `title`; decorative external-link icons are hidden
  from assistive technology. Existing button focus-visible styles remain.
- The number is the frozen item's `position + 1`, not its appearance order or
  current analysis-page offset. Multiple references to one source keep their
  number, and the test exercises reversed paragraph order plus a repeated ID.
- Rendering remains behind `validateAISummarySources`: cited IDs must belong to
  completed relevant sources in the same frozen summary/run/platform. The
  unchanged API decoder validates stored URLs, unique identities and contiguous
  positions across the full bounded source set. Invalid references suppress the
  report; the component never derives a link from model prose or current result
  pagination. React continues to escape model HTML/Markdown as ordinary text.
- Douyin, Weibo, Kuaishou and Toutiao citations are semantic anchors using the
  exact stored `content_url`, `_blank` and `noopener noreferrer`. No URL
  reconstruction or new platform action was introduced.
- XHS remains the existing Shadcn link-styled button and shared stored-result
  action. Pending state disables all competing XHS controls; the active source
  keeps its busy state/label, and bounded feedback remains a nearby status
  element. Fixtures verify Tab/Enter operation, one open action, pending lock,
  error recovery, and absence of a fabricated XHS anchor. These are simulated
  application-boundary tests, not a live XHS opening.
- Analysis rows retain their original labels, markup behavior and links. The
  diff contains no backend/schema/model/prompt or generation-lifecycle change.
  The one pre-existing version-selection test adjustment simply waits for the
  asynchronously rendered option with `findByRole`.

## Independent verification

Executed in `/tmp/longtian-media-validation.DeYMEC/frontend` using mise Node
**24.20.0** and pnpm **11.14.0**:

```sh
mise x node@24 pnpm@11.14.0 -- pnpm install --frozen-lockfile
mise x node@24 pnpm@11.14.0 -- pnpm format:check
mise x node@24 pnpm@11.14.0 -- pnpm lint
mise x node@24 pnpm@11.14.0 -- pnpm typecheck
mise x node@24 pnpm@11.14.0 -- pnpm test:run
mise x node@24 pnpm@11.14.0 -- pnpm build
```

- Frozen install and formatting: **PASS**.
- Oxlint: **PASS**, 70 files, zero warnings/errors.
- TypeScript: **PASS**.
- Full Vitest: **288 passed / 14 files / zero skipped**, 7.92s; includes all
  **26** collection-summary tests. The implementer's separate focused 26-test
  run is prior evidence, not a second independent focused invocation here.
- Production build: **PASS**. Local scoped `git diff --check`: **PASS**.
- The first node-only mise invocation stopped before installation because the
  pnpm shim lacked a selected version. Explicitly selecting the already
  available pnpm 11.14.0 resolved tooling selection; no global configuration or
  dependency change was made.

Unchanged backend/MediaCrawler suites were not rerun for this frontend-only
increment. Their earlier results are not represented as fresh evidence.

## Main-session browser evidence and limits

Main's separate saved-summary-6 smoke recorded the citation inside its report
paragraph, persistent underline, exact saved Douyin href and visible focus via
locator focus. At the observed default report width of 380 CSS pixels,
client/scroll widths matched and the console had no warnings/errors. The
analysis disclosure remained available. Summary identity/status/finish time and
2 requests / 13,518 tokens remained unchanged.

That browser check was main-run, not independently replayed here. No live XHS
opening, live Tab-order sequence or wider breakpoint matrix is claimed. The
unit keyboard tests and observed default-width smoke establish their respective
bounded checks, not universal accessibility or platform acceptance. No new
model request, source acquisition, runtime access, Git write, commit, push or
archive was performed by this review.
