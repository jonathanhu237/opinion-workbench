# Early enrichment contract check — 2026-08-28

Scope: independent, bounded contract review, not final implementation acceptance.
Read the check manifest, child PRD/design/implementation plan, parent media/transport
contracts and referenced specs; inspected only the relevant current worker, decoder,
staging, coordinator and recovery boundaries. Implementation was still in progress.
No product files were edited and no tests, runtime, browser, provider or Git operations
were performed. This report is the only reviewer-written file.

## Findings requiring convergence before integration

### C1 — Distinguish a previous idle disconnect from the current request

The initial protocol's events section allowed no enrichment lifecycle marker, while
requiring a busy disconnect to follow its correlated terminal result. The existing
worker can emit an idle `session(disconnected)` immediately before reading an already
queued command. The backend may have installed the new active request before receiving
that frame; its existing `_handle_event` comment expressly documents this race.
The initial enrichment branch instead rejected every session event while enrichment
was active. That incorrectly recycles an otherwise valid new request.

Main accepted a private-protocol refinement during this review: emit one strictly
correlated `accepted` event before browser/staging work; allow the old idle-session
case only before acceptance, then require terminal-before-session for a busy request.
All terminals require acceptance. This changes neither auth/search frames nor UI
progress. Owners are implementing it; this review does not claim it is verified.

Required regressions: idle event queued before command read; duplicate/mismatched
acceptance; terminal before acceptance; post-acceptance unscoped disconnect; correct
`accepted -> terminal(browser_disconnected) -> session`; late old-generation events.

### C2 — Make terminal delivery a writer-settlement and cleanup boundary

The ownership section names who removes files but initially does not define when it
is safe to transfer that responsibility. Awaiting cancellation of an async task alone
does not settle a delegated file-writing thread or an owned probe subprocess.
Furthermore, `auth_worker.serve` prioritizes a matching cancel when the operation and
command complete together: an asset may already be published while its result has
not yet been emitted. Cleanup only in an operation's `CancelledError` branch misses
that window.

Define a terminal result, including cancellation/error, as proof that all owned
download/staging writers and probe processes have settled and cannot publish later.
Backend cleanup and owner release follow this fence, including repeated caller
cancellation and invalid-result handling. A forced-worker fallback must establish
actual process exit before claiming the same guarantee: existing
`terminate_owned_process_group` suppresses the final wait timeout, and
`_recycle_generation` suppresses terminator exceptions, so return from recycling alone
is not exit proof. If quiescence cannot be proved, fail closed and isolate that
operation rather than claiming successful cleanup or permitting overlapping work.
No broad cleanup of historical operations is requested.

Required regressions: delayed writer/probe on cancel and disconnect; repeated cancel
during cleanup; published file plus cancel in the same dispatch turn; invalid manifest
after staged assets; worker death before descriptors arrive; acknowledged cancellation
versus unconfirmed kill; no late file creation after cleanup/next admission. The
backend may clean validated flat entries inside its exact owned operation capability,
but must never scan or recursively remove unrelated root contents.

### C3 — Give both validators the same completeness rules

The draft consumers already differed on observable acceptance: fork permits an empty
modality list and wholly empty `ready` content, while backend rejects them; fork checks
asset-kind/modality consistency only for `ready`, backend for all statuses; backend
requires each asset issue to have its matching top-level issue, fork initially did not.
Conversely, backend checked modality uniqueness but not the protocol's fixed order.
These disagreements can turn a worker-normalized partial result into an internal
protocol failure. The inventory and normalized-content sections should specify these
rules explicitly, with shared golden accept/reject payloads on both sides.

The important ready image/video inventory and audio correspondence are already
represented in both draft validators; no replacement model is recommended. Require
known-media-without-assets, empty text-only content, unknown inventory, cover-only,
partial media, duplicate handles/issues and reordered modalities as parity cases.

## Additional required regression obligations — no new design blocker identified

- Frame/manifest: exact UTF-8 prefix/newline-inclusive 64 KiB boundary, multibyte and
  escaped text fallback, exact 192 KiB manifest boundary and one-byte overflow. An
  over-limit manifest must yield a fixed failure plus owned cleanup, never truncation.
  Inline and manifest forms need identical strict JSON, identity, budget and coverage
  validation, including command UUID/platform/content-ID correlation.
- Files: trusted root and operation identity, UUID4-only handles, no-follow directory
  access, file ownership/mode/single-link checks, replacement/symlink/hard-link attacks,
  size/hash mismatch, duplicate/aliased descriptors and atomic no-replace publication.
- Download/probe: exact code-owned CDN scope, lookalike hosts, private/loopback/link-local
  addresses, DNS rebinding, pinned TLS/Host, redirects, proxy environment and credential
  non-forwarding. Probe only owned local files with network disabled and bounded
  process/output lifetime. Missing/absent/unknown audio or unsupported codecs must not
  become complete audiovisual evidence; a cover is never a video substitute.
- Browser: current-generation trusted-page retention, pre-existing tabs and handed-off
  pages remain untouched; cancellation closes only this operation's page. Do not reuse
  `finish_search_page` unchanged for narrow enrichment cleanup: its fallback calls
  `close_owned_pages`, broader than the new operation-only contract. Preserve the
  existing manual show/close, paused recovery and coordinator exclusion semantics.
- Acquisition stays exact-source and bounded: XHS uses only its approved first-term,
  first-page lookup; other platforms gain no search fallback. No AI call, new schema,
  public download API, generic crawler, transcode or authentication bypass is implied.

## Verification and verdict

Static review only. Lint, type-check and tests were not run in this early pass; main
owns the isolated Centaurus gates. No live platform/media support is certified.
C1 has an accepted resolution; C2/C3 require owner convergence and regression proof.
Implementation may continue within the approved scope, but final quality acceptance
must wait for those checks and the separately dispatched full review.
