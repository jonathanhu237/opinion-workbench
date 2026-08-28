# Enrichment implementation check — bounded pass, 2026-08-28

Status: **PASS for the reviewed shared/offline boundaries; child remains in progress**.
This follows `enrichment-contract-check.md`, but reviews concrete implementations.
The backend and fork owners were editing concurrently. Only this report is written
by the reviewer; product changes and tests belong to the implementers/main session.

## Scope and method

Loaded the current check manifest, PRD/design/implementation plan and revised wire
contract, with the applicable backend/auth/search/recovery and submodule context.
Inspected backend `enrichment_models`, `enrichment_staging`, `content_enrichment`
and the enrichment branch of `media_crawler_auth_worker`; fork `product_media`,
`enrichment_worker_protocol` and the relevant persistent-worker lifecycle; plus their
direct fixtures, repository-source lookup and coordinator touch points. This is not
a final review of all five platform extractors.

No tests, lint, browser/provider calls, user runtime/credentials or Git operations
were performed by this reviewer. Main owns Centaurus synchronization and gates.

## Concrete findings and current disposition

### I1 — Backend allocation failure leaked its newly created operation directory

`MediaSpool.create_operation` originally closed descriptors when `fsync(root_fd)`
failed after directory creation, but did not remove the operation. Since the call
never returned, `EnrichmentSession._operation` was not assigned and service cleanup
could not recover it. This was a concrete allocation rollback gap, not a hypothetical
startup orphan scan requirement.

**Owner-fixed; static fix checked.** The exception path now removes only the empty
directory whose current name still matches the held operation descriptor, and always
closes descriptors. Added `test_allocation_fsync_failure_cleans_only_its_proven_empty_directory`
covers both ordinary failure and directory replacement while preserving root/neighbors.
Main subsequently reported the revised backend full gate:462 passed in8.59s,
with Ruff and formatting clean. This is main-run evidence, not reviewer execution.

### I2 — Fork post-open allocation failures leaked a descriptor

`MediaStaging.create` originally performed `fchmod`/`fstat` after opening a `.part`
file without an exception cleanup boundary; a failure could leave an unregistered
file descriptor in the persistent worker. Backend directory cleanup cannot close
that descriptor.

**Owner-fixed; frozen shared source and regression inspected.** The descriptor is now closed
on failure. Inode identity is registered before `fchmod`, allowing narrow rollback;
an unproven name after failed `fstat` is left to the backend's exact operation cleanup.
`MediaStaging.open` also closes its descriptor if `fstat` fails.
`test_staging_allocation_failure_closes_its_fd` injects both failures and checks the
actual descriptor is closed; only the unproven name is preserved for backend cleanup.

### I3 — Explicit relative probe executable escaped the startup contract

`MediaProbe._video` originally called `Path(candidate).resolve()` before checking
absoluteness, turning a relative explicit `MEDIACRAWLER_FFPROBE` value into an accepted
absolute executable. That differs from the contract's trusted absolute override and
separate PATH-discovery route.

**Owner-fixed; frozen shared source and regression inspected.** Explicit non-absolute
values are rejected before resolution. `test_relative_explicit_probe_is_rejected_without_launch`
proves this without spawning a child; normal resolved PATH discovery remains available.

### I4 — Repeated cancellation could break the promised terminal fence

Initial image inspection used a shielded thread task but awaited it unshielded after
the first cancellation. A second cancellation could cancel that task while its thread
continued. Probe cleanup used an unprotected `process.wait()`, and session cleanup
directly awaited its cancelled operation. These paths did not implement the newly
agreed writer/probe quiescence fence.

**Owner-fixed for normal terminal/cancellation paths; final full gate passed.**
`settle_owned_task` shields the underlying task and distinguishes new caller
cancellation using `caller.cancelling()` increments; intentional child cancellation
does not count as caller interruption. Session disconnect/finally and emitter cleanup
use that discipline. Image threads, delayed probe creation and probe reaping are
drained; failed `kill` does not skip the wait. No terminal is emitted merely because
an await was cancelled. Delayed `new_page` replies are likewise drained and only their
returned page capability is closed.

Inspected regressions include repeated image cancellation, delayed probe creation,
failed-kill/delayed-exit, same-turn completed-operation/cancel, real session manifest
success, real session disconnect and intentional child cancellation. The latter two
explicit sentinels were added without a source change. An interim reviewer concern
about unconditional `interrupted=True` used an older helper snippet; it was withdrawn
after refreshing the frozen source, and is not a new defect/fix or red test claim.
See the separate abnormal-worker-death limitation below: writer exit is not proof of
whole-process-group exit.

### I5 — Remaining concrete cross-end validation mismatches

Beyond the initial C3 inventory issues, the backend originally allowed int64 media
dimensions/duration while the fork limited dimensions to32768 and duration to the
safe-integer range. Backend WB/KS source validation reused a looser historical search
helper, and the fork initially lacked backend's NUL/strict UTF-8 text checks.

**Owner-fixed; shared corpus inspected.** Backend checks ASCII source IDs, DEL-free
URLs and matching numeric ranges; fork checks NUL and strict UTF-8. The shared corpus
contains these invalid inputs plus blank/empty ready content, missing video, partial
asset/modality/issue consistency and canonical modality order. Main reported54 passing
backend tests across the latest three enrichment suites with this corpus. Historical
search URL acceptance was not broadened or replaced.

### I6 — First-party terminal HTTP status could be masked by its response body

`BoundedPlatformClient._request` initially read/validated the body before returning
status to the existing business classifier. A403/429 with an oversized, encoded or
stalled body could therefore become `structure_changed`/`timed_out` rather than the
already known block category.401 was similarly vulnerable. The parent media audit
requires those categories to remain distinct; downloader/navigation already handle
known HTTP terminal statuses first.

**Owner-fixed; frozen source/regressions inspected, final full gate passed.** Known
terminal statuses now precede body processing. `test_terminal_http_status_wins_without_reading_any_error_body`
uses an unreadable body with oversized/compressed headers and asserts the fixed
outcome, closure and one request.200 business JSON and302 no-follow behavior remain.
The first fix mapped XHS461/471 globally; review caught that cross-platform drift.
It is now restricted to `edith.xiaohongshu.com`, with a two-origin regression proving
KS461 remains an empty-body response for its original platform classifier.

### I7 — Page-close failure was consumed without failing acquisition

`owned_page` initially awaited its closing task only through `settle_owned_task`,
which deliberately consumes task exceptions. The existing manager keeps ownership
when `page.close()` fails, but the wrapper did not inspect that failure and could
allow acquisition to return completed. This is distinct from cancellation draining.

**Owner-fixed; frozen source/regressions inspected, final full gate passed.** Both cleanup
paths use `_close_created_page`, which checks cancellation, exception and explicit
false return after settlement. A failed close becomes constant `internal_error`,
preserving the owned capability. New tests use the real `CDPBrowserManager` with a
failing fake page to cover normal exit and delayed-creation cancellation without raw
error leakage or touching an unrelated page. The old global CDP manager is unchanged.

## Known abnormal-worker-death limitation — explicitly accepted by main

The probe inherits the worker's process group; its only media input is a read-only
descriptor, it has no browser/provider role, and its command has no output file or
network protocol enabled. On an ordinary terminal path the worker waits for it.

However, if the worker itself has already exited, backend `_recycle_generation`
skips the terminator because `returncode` is known. Both the enrichment finally guard
and `EnrichmentWorkerUnsettledError.quiescent()` also examine only that captured
worker return code. The code does not check or reap the remaining process group.
The10-second probe timeout lives in the worker coroutine and is not an independent
child-process hard deadline after that worker dies.

Main explicitly chose not to expand this into a global process-manager redesign:
confirmed worker exit ends all staging writers, permitting narrow cleanup of this
operation's files; a potentially surviving read-only probe cannot publish new files
or continue browser/provider operations. The revised protocol now explicitly says
**worker-process exit proving no remaining staging writer**, not confirmed whole-group
exit, and retains possible read-only probe residue as an unresolved resource-reclamation
limitation. This wording was re-read and matches the implementation. No real residue,
zero-orphan guarantee or complete child-task acceptance is claimed by this review.

## Boundaries positively traced in the reviewed code

- `accepted` is emitted synchronously on command admission before the task can run;
  the backend tracks it, permits only the old pre-accepted idle-session race, and
  rejects duplicate acceptance/result-before-acceptance/wrong request identity.
- Source lookup proves run/content relation and ordered stored matched terms in one
  read snapshot. The service rejects active/paused collection sources before worker
  or spool work, uses one serial coordinator lease, and introduces no database writes
  or model calls. Threaded acquisition is shielded from caller cancellation, and
  cleanup follows worker completion/confirmed exit rather than merely sending cancel.
- File reads use held directory descriptors, no-follow opens, owner/mode/link checks,
  bounded sizes, hashes and inode identity checks. Backend cleanup is flat and limited
  to its owned operation capability, not a startup/root sweep.
- Downloader uses exact configured CDN hosts, rejects unsafe URL shapes and nonpublic
  DNS answers, pins the selected address with original Host/TLS name, disables proxy,
  redirects/retries and ambient Cookies, and enforces streaming byte/time bounds.
- Images undergo bounded single-frame decoding; video probing is local-only with
  network protocols disabled and explicit audio/codec checks. Non-ready media is not
  converted to ready by the backend. Large normalized content uses the bounded
  manifest path rather than truncating source text to fit the64KiB frame.

## Verification and remaining acceptance

Intermediate snapshots were429 passed/3 failed (fixture mistakes/missing synchronized
corpus), backend462 passed after I1, shared fork108 passed before the last narrow
patches, platform suites91 passed, and backend enrichment suites54 passed against the
updated corpus. They are historical stepping stones, not the final evidence.

After final source freeze and import-order convergence, main reported these Centaurus
results; the reviewer did not independently execute them:

- Full fork: **867 passed in20.19s, zero skips**, one inherited SQLAlchemy warning.
- Full backend: **462 passed in8.94s**; backend Ruff and format checks passed for58 files.
- Fork scoped static gate: `ruff --isolated check --select E4,E7,E9,F,I` and
  `ruff format --isolated --check` passed for16 owned files. This is the stated
  selected-rule gate, not a claim that all legacy fork Ruff rules are clean.
- Separate type-checker run: not reported/not claimed; this pass relies on the
  explicitly reported lint/format/tests and static boundary review.
- Main's task-only `verification/offline_probe.py` used real ffprobe9 on synthetic
  media: H264/AAC MP4,6973 bytes,64x64,1065ms, audio present succeeded; a silent MP4
  returned `audio_missing`; both temporary staging scopes were empty afterward.
  A PATH executable with mode775 was correctly rejected; copying only its binary
  failed due to missing RPATH libraries. The successful isolated0700 tool copy used
  the existing libraries read-only, without modifying system tools or production.

All concrete shared-boundary findings I1–I7 are resolved in the reviewed source and
covered by the reported final offline gate. The separately documented abnormal-death
read-only-probe resource limitation remains open by explicit main-session decision.
No runtime/browser/provider operation, product edit or Git operation was performed
by this reviewer.

The reviewed downloader's production CDN allowlists are still empty pending approved
exact-source browser/CDN evidence. This is an unfinished dependency, not evidence that
media acquisition works on any platform. Douyin/Toutiao canonical entry points still
explicitly return `structure_changed`; their fixture safety is not a finished extractor.
Fixture success, unavailable outcomes and prior standalone probe results do not
satisfy the child live media gates. No final five-platform, full implementation, UI,
model or Git-delivery acceptance is given here.
