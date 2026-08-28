# Enrichment wire and staging contract — v1

Frozen implementation contract, 2026-08-28. This supplements the approved child
design; existing auth-v2 and search-v2 frames are unchanged. No provider is called.

## Ownership and startup

- Backend supplies an absolute trusted `MEDIACRAWLER_MEDIA_ROOT` in the persistent
  worker's startup environment. Missing root disables enrichment only; auth/search
  remain usable. No command accepts a filesystem path or download URL.
- Backend creates the root and each operation directory privately, mode 0700,
  current UID, no symlink components. The operation basename is `UUID(request_id).hex`
  (32 lowercase hex characters). Worker requires this existing empty operation
  directory; it never creates a caller-selected root or operation directory.
- Both sides retain/check directory identity and use directory-relative no-follow
  file access. Asset/manifest handles are random UUID4 hex strings. The file is
  exactly `<root>/<request_id.hex>/<handle>` (no extension, suffix or path segment).
  Files are current-UID, single-link regular files, mode 0600. A worker-owned
  `.<handle>.part` is atomically published without replacing an existing handle.
- Worker removes only its registered partial/staged files on error/cancel. On a
  completed result, backend owns reading/validation and removal after consumption,
  including invalid-result handling. Backend also removes its proven operation
  directory. No startup scan, broad recursive delete or expiry-based ownership guess.
- Every terminal frame is a writer-quiescence fence: owned downloads, thread work
  and ffprobe children settle before it is emitted. Cancellation winning after task
  completion but before emission still discards published owned files. Backend cleans
  only after a terminal frame or confirmed worker-process exit proving no remaining
  staging writer, never after merely sending cancel. Oversized manifest construction
  has the same cleanup guarantee.
- Abnormal worker death is a weaker fallback than an orderly terminal: the backend
  proves worker exit, not exit of the entire process group. A surviving ffprobe
  inherits only a read-only media descriptor, cannot write staging or operate the
  browser/provider, and its timeout lived in the now-dead worker. It may therefore
  outlive that worker; zero orphan processes and a child-independent hard deadline
  are not established. Keep this resource-reaping limitation open rather than
  treating worker `returncode` as whole-group proof. Normal cancellation/terminal
  still waits for owned probe and thread settlement.
- Optional startup `MEDIACRAWLER_FFPROBE` is a trusted absolute executable path;
  otherwise discover `ffprobe` on PATH and validate the resolved regular executable.
  Missing/unsafe probe yields an explicit asset issue, not audio proof. Probe only
  owned local files with network protocols disabled, bounded output and timeout.

## Commands

Prefix `__MEDIACRAWLER_ENRICHMENT_COMMAND__`, version **1**, newline-terminated UTF-8.
Complete command (including prefix/newline) is at most **32 KiB**. Strict JSON:
duplicate keys, NaN, unknown keys, coercion, malformed UUIDs and invalid types fail.

```json
{"version":1,"type":"command","command":"enrich","request_id":"<canonical-uuid4>","platform":"dy","content_id":"<stored-platform-id>","content_url":"<stored-canonical-url>","term":"<first-stored-matched-term>","budget":{"max_text_chars":20000,"max_images":24,"max_videos":1,"max_total_bytes":6291456}}
```

- Platforms exactly `wb|dy|ks|xhs|toutiao`. Stored ID is nonempty, at most128 chars;
  DY numeric, XHS lowercase24hex; other IDs follow their existing canonical routes.
  `content_url` is at most2048 chars, identity-matching canonical official URL;
  no credentials, fragments, explicit ports or token/query values. Toutiao accepts
  only its recognized canonical article/video/micro-post route, not search/external.
  WB/KS IDs are ASCII alphanumeric/underscore/hyphen. Toutiao is exact HTTPS netloc
  `www.toutiao.com|m.toutiao.com|toutiao.com`, full-match paths
  `/(article|group|video)/<numeric-id>`, `/[ai]<numeric-id>` or `/w/a?<numeric-id>`,
  with at most one trailing slash and the stored numeric identity unchanged.
- One observed legacy exception accepts only
  `http://www.toutiao.com/a<same-numeric-id>` with an optional single trailing slash,
  without query, fragment, credentials or port. The paired validators preserve
  that exact stored URL for command/result correlation; the Toutiao adapter upgrades
  to HTTPS **before its single navigation** and verifies the final article ID.
  No other HTTP source is accepted, and no stored row is rewritten.
- `term` is a string of 0–200 chars. XHS requires a nonblank first matched term for
  its one approved first-page lookup; other adapters do not perform search fallback.
- Budget has exactly four strict integer fields, each positive and at most the
  shown hard cap. These are acquisition caps, not promises of model compatibility.
  No probe-only90-second duration limit is adopted. Media is one self-contained MP4
  plus up to24 actual JPEG/PNG/WebP images; aggregate raw bytes at most6MiB.
- No raw title, HTML, auth state, source term or locator is logged.

Cancellation has only `version,type,command:"cancel",request_id`. Only a matching
active enrichment request can be cancelled. Shutdown remains auth-v2 shutdown.
Enrichment has a120-second total worker deadline; downloads have30-second total,
10-second connect/read bounds; ffprobe has10seconds and64KiB stdout. Backend may
use150seconds including cancellation/cleanup; this is not a media-duration limit.

## Events

Prefix `__MEDIACRAWLER_ENRICHMENT_EVENT__`, version1, at most **64 KiB** including
UTF-8 prefix/newline. Exactly one correlated `accepted` lifecycle marker, then exactly
one terminal result; no UI progress frames. Accepted is emitted synchronously at
command admission before any browser/staging work, including immediately cancelled
or failed commands. It contains exactly version,type,event,request_id,platform,content_id:

```json
{"version":1,"type":"event","event":"accepted","request_id":"<uuid4>","platform":"dy","content_id":"<same-id>"}
```

Backend permits an idle auth-session/disconnected frame only before accepted; after
accepted a busy disconnect requires the correlated result first. Reject duplicate
accepted, result-before-accepted and wrong identities. Auth/search lifecycle is unchanged.

```json
{"version":1,"type":"event","event":"result","request_id":"<uuid4>","platform":"dy","content_id":"<same-id>","outcome":"completed","content":{},"manifest":null}
```

`outcome` is exactly one of:

`completed | login_required | manual_challenge_required |
platform_blocked_or_rate_limited | lookup_miss | content_unavailable |
structure_changed | browser_unavailable | browser_disconnected | timed_out |
staging_unavailable | cancelled | internal_error`.

`completed` means a normalized acquisition result exists, **not** that input is
complete. Exactly one of `content` and `manifest` is non-null for completed; both
are null for all other outcomes. A cancelled result is solicited only. A busy
disconnect emits its correlated result before the auth session-disconnected event.
Unknown/duplicate/out-of-order/mismatched events recycle the worker, not success.

If the full normalized projection would exceed64KiB, stage its UTF-8 strict JSON
instead; never truncate source text to fit a frame. The descriptor is exactly:

```json
{"handle":"<uuid4-hex>","byte_size":123,"sha256":"<lowercase64hex>","mime_type":"application/json"}
```

Manifest maximum is **192 KiB**; its content is precisely the same normalized
object as inline `content`. Decoder, source identity, caps and coverage validation
are identical. Backend verifies bytes/hash/private ownership before parsing it.

## Normalized content (all fields required)

```text
{
 schema_version: 1,
 platform: same platform, content_id: same stored platform ID,
 content_url: same canonical stored URL,
 acquired_at: integer Unix milliseconds (13 digits),
 extractor_version: "<platform>-enrichment-v1",
 status: ready | partial | unavailable | unsupported,
 text: {title: string, body: string, coverage: complete | partial | unavailable},
 detected_modalities: ordered unique subset of [text,image,video,audio,unknown],
 media_inventory_complete: boolean,
 assets: [MediaAsset],
 issues: [{code: IssueCode, asset_position: integer|null}]
}
```

- `title` at most1000 chars; `title` + `body` at most budget.max_text_chars.
  An over-limit body is unavailable with `text_limit`, never a silent prefix.
  A visibly clipped body may be retained only as partial with `text_incomplete`.
  NUL and unpaired Unicode surrogates are rejected; all text must encode as strict UTF-8.
- Modalities are nonempty, unique and in the listed canonical order. Every asset kind
  is declared, including non-ready assets. Every non-ready asset's issue has a matching
  top-level issue/position; every referenced top-level issue matches that asset. Duplicate
  `(code,asset_position)` issues are invalid.
- At most25 ordered assets, positions contiguous from0. Covers/avatars/recommended
  images are not assets. A known video with only a cover stays an unavailable video,
  with `cover_only`; it must never be relabelled as an actual image.
- `ready` requires complete text and media inventory, every asset ready, no issues
  and no unknown modality. Zero assets proves text-only only with complete inventory.
  Ready also needs nonblank observed text or an actual ready asset; empty captions
  remain valid with complete real media, never as all-empty ready input.
  All other statuses require at least one explicit issue. `partial` retains usable
  observed text/assets without claiming full input; it is not model-ready.
- Backend attaches its stored integer source ID and computes its evidence fingerprint
  after validation; neither is worker-controlled. Fingerprinting excludes request IDs,
  opaque handles, acquisition time and ephemeral URLs.

```text
MediaAsset {
 asset_id: uuid4-hex, position: int, kind: image | video, role: content,
 status: ready | unavailable | unsupported | failed,
 blob_ref: uuid4-hex|null, sha256: lowercase64hex|null,
 mime_type: image/jpeg | image/png | image/webp | video/mp4 | null,
 byte_size: int|null, width: int|null, height: int|null, duration_ms: int|null,
 audio_track: present | absent | unknown | not_applicable,
 coverage: complete | partial | unknown, issue_code: IssueCode|null
}
```

Ready asset: blob_ref equals asset_id, verified nonempty bytes/hash/MIME/dimensions,
coverage complete, issue_code null. Images have null duration and not_applicable
audio. MP4 has positive duration_ms and a verified audio track present. No more than
40million decoded pixels per image; reject bombs/multiple-frame images. Supported
MP4 video codecs h264/hevc and audio codecs aac/mp3/opus only; absent/unknown audio,
unsupported streams or codecs are explicit non-ready assets, never audiovisual proof.
Non-ready asset: blob_ref/sha256/mime_type/byte_size/width/height/duration_ms all null,
coverage unknown, non-null issue_code; image audio not_applicable, video audio unknown.
Ready assets collectively satisfy all requested count/byte budgets. Issues are at
most32 entries; an asset_position must refer to an existing asset with that issue.

IssueCode allowlist:

`text_incomplete, text_unavailable, text_limit, inventory_unknown, media_missing,
cover_only, asset_unavailable, asset_expired, download_failed, download_timeout,
asset_blocked, unsafe_media_url, media_redirect, media_limit, image_limit,
video_limit, invalid_media, unsupported_transport, unsupported_media_type,
unsupported_codec, audio_missing, audio_unknown, probe_unavailable, probe_failed,
structure_changed`.

## Fork symbols and integration

- `tools/enrichment_worker_protocol.py`: `EnrichmentCommand`,
  `EnrichmentCancelCommand`, `EnrichmentBudget`, `EnrichmentAcceptedEvent`, `EnrichmentResultEvent`,
  `EnrichmentOutcome`, `parse_enrichment_worker_command`,
  `serialize_enrichment_worker_event`, `validate_enriched_content`.
- `tools/product_media.py`: `MediaStaging`, `MediaDownloader`, `MediaProbe`;
  internal locators/headers never serialize. Stream-capped HTTPS with a code-owned
  per-platform CDN allowlist, checked public DNS pinned to TLS SNI/Host, no proxy,
  redirect or retry; no Cookie/Authorization sent to CDN downloads.
- Each `media_platform/<platform>/product_enrichment.py` exports
  `async enrich_with_context(*, browser_context, cdp_manager, command, staging,
  downloader, probe) -> dict` (normalized content) or raises the shared fixed
  enrichment outcome exception. Pure platform projection helpers are fixture-tested.
- `WorkerBrowserSession.enrich(command) -> EnrichmentResultEvent` uses the startup
  root, creates no browser until an accepted command, races disconnect/cancellation,
  and closes only its registered operation page. Recognized manual login/challenge
  may retain that trusted owned page using existing narrow recovery ownership.
- Existing page handoff, auth callbacks, search completions and cancellation retain
  their exact prior behavior. No generic crawler/store/client is called.
