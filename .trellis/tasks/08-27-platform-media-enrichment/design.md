# Platform Media Design

Use parent design section B and `../08-27-multimodal-opinion-analysis/research/platform-media-plan.md`. The report's per-platform source facts are candidates, not live-support claims. Model envelope constraints come from `research/model-transport-contract.md` in that same parent.

Post-probe design refresh: also read the parent's `research/product-integration-readiness.md`. The Douyin exact canonical-page heading/player approach is now the first bounded implementation candidate; it needs a pure extractor, source-ID/full-caption checks, fixture coverage and product live acceptance. The probe does not authorize browser-storage extraction, generic detail endpoints, automatic fallbacks, extra searches or a hard-coded CDN URL. Other platforms retain their independently validated narrow paths.

## Boundary

Create a dedicated enrichment command/protocol owner within the fork's `tools/` product-worker integration, with narrow platform projections next to existing product adapters. Backend `services/media_crawler_auth_worker.py` validates the new command/result and a new `services/content_enrichment.py` owns repository identity lookup, browser ownership and temporary asset validation. Do not alter normalized search-item schemas to carry media.

The request uses stored platform/content identity, necessary stored first matched term, UUID and budget; no user-provided download URL. The worker verifies identity before projecting fields. Original page/media URLs are ephemeral worker inputs only.

Enriched projection contains bounded text and explicit coverage, asset kind/MIME/size/hash/opaque handle, extractor/input version and constant outcomes. A generated operation directory under the ignored runtime media root is the only binary handoff. Resolve handles under that directory, reject symlinks/path traversal and verify hashes and caps before model input construction. The backend—not child output—owns path derivation.

Use bounded streaming media downloads and validated platform/CDN hosts/redirects. Platform credentials needed for a specific request remain in worker memory and are scoped to that allowed origin; do not forward them across hosts. Avoid whole-response buffering without enforceable limits. Unsupported playback requiring playlist assembly or protected streams is an honest incomplete result. Probe only staged local MP4 files with bounded, network-disabled `ffprobe`; check codec/audio metadata without conversion. It is available through mise on Centaurus at planning time, but the implementation must verify the resolved tool and handle absence explicitly.

Preserve the current 64-KiB UTF-8 IPC limit. If normalized full text/metadata cannot fit with the fixed envelope, transfer a bounded normalized manifest by opaque handle, using the same ownership/path/hash rules. Do not truncate multibyte text to manufacture a complete response.

Ordinary search/catalog state remains unchanged. `EnrichedContent` is an internal contract, not a generic public file/download API. The integrated manual-summary child later stores immutable source/media metadata; this child requires no product database migration and no model dependency.

## Compatibility

Add the new browser-operation owner to the shared coordinator and keep mutual exclusion with search, batch, login and XHS-open. Preserve protocol validation, request matching, cancellation and owned-tab cleanup. Existing worker clients must fail clearly on unsupported protocol revisions, not interpret enrichment as search/auth success.

Re-read the current manual-recovery integration before changing the persistent worker or browser owner; the original audit's search-v1 assumptions are historical. Preserve recovery's paused ownership, checkpoint proofs and existing page handoff. The new internal enrichment result must not be misread as a search-resume callback. The current schema is v10 but this child adds no migration.

Fork changes must be versioned separately and reachable remotely before a future parent gitlink publication. No vendor source copying. This planning child does not authorize a commit/push by itself.
