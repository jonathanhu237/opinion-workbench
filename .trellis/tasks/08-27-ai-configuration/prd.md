# AI 配置与连接测试

## Goal

Let the local user save and test one AI configuration without editing code. Parent: `../08-27-multimodal-opinion-analysis/prd.md` (R2, R6–R9). This independently usable child has no implementation dependency. The user approved the reviewed plan and starting this configuration child on 2026-08-27.

## Requirements

- Three fields only: API Key, Base URL, model name; one active configuration shared by future screening and summary.
- Save persists across restart without making an external call. Explicit `测试连接` uses the saved values and synthetic text, never collected content.
- Keep the saved key backend-only, replaceable and absent from GET responses, browser storage/query caches, logs and Git. Changing Base URL requires a newly entered key.
- Use existing shadcn components/style and concise Chinese feedback. Do not add provider profiles, automatic model selection, decorative status cards or a general settings dashboard.
- Local permission-protected secret files are the proposed initial store, not encryption. Reject unsafe storage rather than silently weakening protection; the final parent review must disclose this boundary.

## Acceptance Criteria

- [x] Save/read/update/reopen works with temporary local storage; unchanged saves preserve revision, new key/configuration increments it.
- [x] Key sentinels never appear in reads, errors, captured logs, TanStack cache, persisted frontend state or task artifacts.
- [x] Key replacement/storage failure is atomic; failed database commit leaves the previous usable configuration intact.
- [x] Wrong types/extra fields, invalid destinations, cross-site origins, stale test revisions and endpoint changes without a key fail with documented codes.
- [x] Save/page load/restart make zero provider requests; one explicit test makes exactly one bounded synthetic request with no retries.
- [x] Test success/failure UI is truthful, keyboard accessible, and never described as multimedia capability validation.
- [x] Existing backend/frontend gates and routes pass; fake transport tests need no real key/network.

Acceptance evidence (2026-08-27): `verification.md` and `research/check-review.md`. Centaurus
passed 308 backend and 136 frontend tests plus frozen package gates; the isolated browser smoke
passed after independent fixes. This is implementation acceptance, not live-provider or macOS/
Windows credential-store certification. User runtime and real credentials were not used. Awaiting
user review and a separately requested commit/archival; later child tasks remain unimplemented.

## Dependency and Exclusions

- Produces the configuration projection/revision, credential lease and bounded model-client contracts consumed by screening/summary. No browser/media/collection database changes in this child.
- Model protocol/limits are defined in the parent's `research/model-transport-contract.md`; no vendor SDK, native protocol adapter or cloud file storage.
- Real provider testing is a later explicitly invoked acceptance step using a locally entered replacement key, never the chat-disclosed credential.

## Approved Follow-up: Saved-Key Mask (2026-08-27)

The user requested that a configured API Key appear as a fixed group of asterisks in its input.
This is a small frontend-only follow-up to the already approved configuration feature. The user
then clarified that these should be normal visible asterisks, not a muted placeholder, and more
numerous. The current acceptance below supersedes the first eight-character placeholder version.

- [x] A saved key is indicated by 20 literal asterisks (`********************`) in normal foreground
  text when the input is empty and unfocused, not by a placeholder or browser password dots.
  Hide the display during focus/typing, restore it on empty blur, and show no mask when unconfigured.
  Preserve the current shadcn input, label and password type for actual replacement input.
- [x] The mask is display-only, independent of the real key and its length. It is never form data,
  a saved payload, a dirty-state trigger or a replacement for the retained backend key.
- [x] Typing, clearing, saving, reopening and failed-save clearing preserve existing behavior.
  Changing Base URL still requires a newly typed key. No provider requests, credential reads,
  backend changes, design restyling, commit or push are part of this follow-up.

Follow-up evidence: `research/saved-key-mask-verification.md` and
`research/saved-key-mask-check.md`. The earlier live-search acceptance is unchanged.

## Additional Approved UI Copy Follow-up (2026-08-27)

The user explicitly requested generic numbered placeholders in the monitoring-rule editor during
this UI-polish session. This separate copy-only request does not change AI configuration scope or
monitoring behavior. Preserve all existing uncommitted work.

- [x] Monitoring objects show exactly `对象 1\n对象 2\n对象 3`; issue keywords show exactly
  `关键词 1\n关键词 2\n关键词 3`, each rendered as three lines in the existing textarea.
- [x] These remain placeholders, not default/form/saved values. Keep labels, validation, query
  composition, existing rules, component styling and API behavior unchanged; no live save/search.

Evidence: `research/monitoring-placeholders-verification.md` and
`research/monitoring-placeholders-check.md`.
