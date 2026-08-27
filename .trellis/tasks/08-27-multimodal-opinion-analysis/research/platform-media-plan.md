# Research: Bounded platform text and media enrichment

- Query: Reusable full-text/image/video enrichment for existing stored Toutiao, Weibo, Kuaishou, Douyin and Xiaohongshu results, before one configurable multimodal relevance model.
- Scope: internal; source/spec inspection and planning only.
- Date: 2026-08-27
- Evidence: **Source** = inspected executable source, not live platform success. **Proposal** = candidate requiring fixtures and live acceptance.

## Findings

### Existing boundary

- **Source:** No product adapter delivers enrichment: metadata-only `SearchItem` (`third_party/MediaCrawler/tools/search_worker_protocol.py:97`), title/snippet ≤300/1000 and no media in `SearchResult` (`backend/src/longtian_api/schemas/search_runs.py:99`). Page links are references, not media.
- **Proposal:** Separate manual enrichment from search/auth; extend current search-only spec explicitly. Reuse ownership/parsers, not crawler loops/stores/retry clients. No comments/profiles, OCR/ASR, text-only semantic discard, second model or broad pagination.
- XHS has exact-ID navigation; WB text/picture patterns; KS media query; DY selectors but incompatible generic detail transport; Toutiao no detail extractor. These are candidates, not proven integrations.

### Per-platform source and bounded plan

Source paths are relative to `third_party/MediaCrawler/`; bare sibling filenames use that row's platform directory.

| Platform | Reusable source functions / anchors | Actual input → output fields | Ephemeral requirements | Simplest proposal and missing pieces |
| --- | --- | --- | --- | --- |
| `toutiao` | `canonicalize_toutiao_url`/`classify_toutiao_url`: `media_platform/toutiao/help.py:103`, `:155`; owned-page lifecycle: `product_search.py:31`; search-only client: `client.py:177`; detail unsupported: `core.py:251`. | Search `href,title,snippet,publisher_name,published_at_text` → discovery. URL patterns classify article/group/legacy article, video, micro-post, trending or unknown/digest (`help.py:38`). **No body/image/player fields or extractor found.** | No detail-token contract found. Borrowed context can supply ordinary session state; stored URLs deliberately remove search/redirect tokens. | One owned-page navigation to validated stored article/micro-post/video URL; new exact-content bounded body/media DOM or hydration projection. Include only content-body images, not recommendations/avatars. Player sources are candidates, not proof. Trending/unknown/external embeds initially unsupported. Selectors, full-body completion, lazy images and video bytes all require live gates; no guessed internal API. |
| `wb` | `WeiboClient.get_note_info_by_id`: `media_platform/weibo/client.py:258`; `get_note_full_text`: `core.py:533`; `get_note_images`: `core.py:376`; HTML-cleaning pattern: `product_search.py:76`. | ID → GET `/detail/{id}` → parse `$render_data` → `[0].status` wrapped as `mblog`; `id,text,isLongText`; `pics[]` is URL string or `{url,pid}`. Store cleans `text` (`store/weibo/__init__.py:82`). **No video locator/stream extraction found.** | Mobile-origin scoped Cookies + mobile UA (`product_search.py:297`). No per-item token parameter. Hotlink requirements/any CDN token TTL unproven. | One single-attempt bounded official detail fetch; factor a pure exact-ID `$render_data` parser, normalize body/ordered pictures. Full-text helper replaces data but swallows failures: not completeness proof. New controlled direct-image downloader, **not** existing third-party proxy. Video needs a verified owned-page player/projection and fixture; no fabricated media API/fields. |
| `ks` | `KuaiShouClient.get_video_info`: `media_platform/kuaishou/client.py:243`; `graphql/video_detail.graphql:1`; unwrap `core.py:342`; store projection `store/kuaishou/__init__.py:55`; product lifecycle `product_search.py:295`. | `photo_id` → GraphQL `visionVideoDetail(photoId,page="search")` → `data.visionVideoDetail.{status,type,photo}`. Query asks `photo.{id,caption,duration,timestamp,coverUrl,photoUrl,videoRatio,musicBlocked,manifest,manifestH265,photoH265Url,videoResource}`; manifest representations include `url,backupUrl,codecs,width,height,avgBitrate,maxBitrate,m3u8Slice,frameRate,qualityType,qualityLabel` (`graphql/video_detail.graphql:12`). | Detail source passes current headers/Cookies, no extra item token. REST search separately requires page-local `__NS_hxfalcon` and searchSessionId (`product_search.py:235`); do not infer detail requirements from search. CDN TTL unknown. | One product-specific single-attempt detail query modeled on existing query, minimized fields, scoped auth, strict status/exact `photo.id`. Select one verified progressive stream with audio; cover is not video. No generic logging/store or blocked-request fallback. Detail liveness/status semantics, media/audio, H265 and image-post representation remain unverified. No downloader found. |
| `dy` | `_extract_note_image_list`, `_extract_video_download_url`, `_extract_content_cover_url`, `_extract_music_download_url`: `store/douyin/__init__.py:54`, `:122`, `:102`, `:142`; `_request_search_page`/`_extract_works`: `media_platform/douyin/product_search.py:326`, `:250`; generic detail shape: `client.py:211`. | `aweme_id,desc,aweme_type`; `images[].url_list`; video preference `video.play_addr_h264.url_list`, `play_addr_256.url_list`, `play_addr.url_list`; covers `raw_cover/origin_cover.url_list`; music `music.play_url.uri`. Detail returns `aweme_detail`. Search exposes raw `data[].aweme_info` or first `aweme_mix_info.mix_items`. All persisted product works are labeled `video` (`product_search.py:130`), not actual modality proof. | Safe path reads only `localStorage.getItem('xmst')` → `msToken`, scoped Cookies and transient search/web IDs (`product_search.py:427`). Generic detail reads **all** LocalStorage and adds `a_bogus` (`client.py:82`, `:119`): incompatible with current product constraints. | Smallest existing-transport candidate: one first-page search for first stored matched term, exact-ID selection, typed raw-work media projection, no other terms/pages/retry. Other-ID rejection is identity selection, not semantic filtering. Only works if target remains on that page; **not general historic-detail coverage**. Missing target → lookup miss; absent media/completeness proof → incomplete. General old-post support needs a new owned canonical-page extractor and separate live gate, not covert generic detail replay. |
| `xhs` | `open_xhs_result_with_context`: `media_platform/xhs/product_search.py:669`; exact note proof `:118`; generic `get_note_by_id`: `client.py:359`; HTML pattern `extractor.py:31`; video selector `store/xhs/__init__.py:54`; images `core.py:721`. | Stored lowercase 24-hex ID + first matched term → search `{id,note_card,xsec_token}` → explore page → `window.__INITIAL_STATE__.note.noteDetailMap[id].note`. HTML extractor decamelizes to `note_id,title,desc,type,image_list`; image `url_default/url`; video `consumer.origin_video_key/originVideoKey` or `media.stream.h264[].master_url`. Feed API returns `items[0].note_card`; browser fields can be camelCase. | Reacquire bounded `xsec_token` in worker memory via exactly one first-page lookup; derive fixed `xsec_source="pc_search"`, never trust response source (`product_search.py:740`, `:761`). Search/self-info reuse scoped existing signer. No token, token URL, headers or raw response persistence. | Factor lookup/navigation into internal helper preserving existing open behavior. Enrichment keeps ownership, projects only matching note after origin/ID proof, then closes its page. Never scrape the handed-off user tab. Strict camel/snake normalization; prefer returned validated HTTPS streams, not fabricated HTTP CDN URLs. Actual images/video/audio unverified. First-page miss is not deletion/unsupported. |

### Reuse hazards

- Weibo `client.py:72` retries/navigates/logs raw responses; `:280` rewrites images via `i1.wp.com`. Kuaishou `client.py:117` retries rate limits. XHS retries/API→HTML fallback (`core.py:489`) and store persists/logs xsec (`store/xhs/__init__.py:126`). Keep these paths unreachable.
- Douyin selector rejects one-URL arrays (`store/douyin/__init__.py:137`); crawler chooses images **or** video (`core.py:511`). XHS image mutation can replace usable `url` with missing `url_default`; video helper guesses HTTP from origin key. New strict pure selectors need tests.
- Existing downloaders read unbounded `response.content`; Douyin `client.py:347` follows unvalidated redirects. No shared capped downloader/prober/HLS/DRM implementation found. Music URI, cover, filename or source comment is not soundtrack proof.

### Proposed shared contract (no secrets)

One versioned internal contract; public/model projections are separate:

```text
EnrichedContent {
  schema_version, enrichment_id, search_content_id, platform, platform_content_id,
  canonical_url, observed_at, extractor_version,
  text: {title, body, coverage: complete|partial|unavailable},
  detected_modalities: [text|image|video|audio|unknown],
  assets: MediaAsset[], media_inventory_complete: boolean,
  status: ready|partial|unavailable|unsupported|failed,
  issues: [{code, asset_id?}], input_fingerprint
}
MediaAsset {
  asset_id, position, kind: image|video|audio, role: content|cover,
  status: ready|unavailable|unsupported|failed,
  blob_ref?, sha256?, mime_type?, byte_size?, width?, height?, duration_ms?,
  audio_track: present|absent|unknown|not_applicable,
  coverage: complete|partial|unknown, issue_code?
}
```

- `blob_ref` is an opaque staged-file handle, never arbitrary path/URL/provider ID. Ready requires verified bytes/MIME/hash; failures retain order/kind/issue. Unknown duration/audio is not zero/absent. Transient download `{url,origin,headers,expiry}` stays worker-only.
- Preserve image order, distinguish covers, collapse only alternate renditions. Report caps/omissions. Complete text + complete inventory is required for complete input; empty media does not prove text-only. No cover/snippet substitution. Empty caption can be valid with complete media.
- Fingerprint observed text, ordered media hashes, coverage/issues and extractor version, not signed URLs/last-seen. Separate revisions from collection; explicit refresh, no automatic recrawl. Cache provenance need not retain bytes forever.
- Missing input is execution state, not a model verdict. Partial screening requires an explicit policy and visible omissions; never silently cache missing-media “unrelated”. Exclude secrets/raw HTML/state/profile fields/raw exceptions.

### Bounded extraction and inline-transfer proposal

1. Prove stored result/run ownership; one exact item per worker command within durable scope, no arbitrary input URL. Verify detail origin/ID. XHS/DY relookup: first stored term, first page only.
2. Register one page in approved borrowed context; scoped auth/page-local signer only. No browser fallback/context scripts/cookie export/whole LocalStorage/challenge actions. Stop on block/login/challenge without retry/reload/fallback. Finite within-content lazy loading needs completion proof; no related-feed/link traversal.
3. Stream downloads with time/byte/count/duration caps; validate scheme/CDN host/DNS/every redirect, reject private/loopback/userinfo/non-default ports, disable environment proxies. Count actual bytes despite false/missing Content-Length. No cross-origin Cookie/Authorization forwarding; Referer/UA only if verified. Establish CDN allowlists from approved live evidence.
4. Check MIME/decodability; reject HTML/corruption/bombs/unsupported codec. Probe staged files only. Preserve original muxed video/audio; no transcode/OCR/ASR/frames/covers/music/screen-capture substitution.
5. Initially approved images/progressive video only. Without an approved progressive alternative, blob/MSE, HLS/DASH, live, DRM/encrypted-only and separate-track assembly are unsupported. No key fetching/playlist assembly. HLS accounting/remux is separate future scope.
6. Owner-only ignored runtime spool: random handles, atomic completion, path/symlink defenses, disk/TTL/cancel cleanup. Retain normalized provenance/hashes separately; delete only validated feature files. No network/model work inside DB transactions.
7. **Main-agent model research option:** backend assembles inline bytes from opaque handles; no OSS/file API/hosting/platform-token URLs. Main verified Qwen3.5-Omni audiovisual `video_url` inline input and **Base64 string <10 MB**. Enforce encoded-string (not raw-file) size, lower operational cap and total request limits. Provider-specific; arbitrary configured models are not guaranteed compatible.
8. Base64 only in backend→provider payload, never worker NDJSON/public API. No AI key in worker/platform Cookies in backend. Close owned per-item pages/finish worker IPC before the model call. Final parent design deliberately retains the product browser-coordinator lease across the screening run, preventing an intervening collection batch from stealing the next enrichment step; this supersedes the initial per-call release proposal. Size/format failure is explicit, no conversion/text-only filtering fallback. Text connection success and retained audio track do not prove actual model audiovisual consumption.

### Error categories and recovery

| Condition | Required distinction |
| --- | --- |
| Known unsupported content type/DRM/manifest-only transport/codec | `unsupported` with stable reason, not retryable success or unrelated. |
| Login, manual challenge, block/HTTP 403/429 | Separate existing categories; stop without retry, preserve only owned official evidence page. Later user action may recover. Do not call every 403 expired. |
| XHS/Douyin first-page exact-ID miss | `lookup_miss`, not deletion; no extra term/page. |
| Verified unavailable/deleted content, XHS official 300031 | `content_unavailable`; retain source history. |
| Positively recognized expired locator | `asset_expired`; explicit refresh only. TTL is not established by source. |
| Wrong ID/unknown schema/missing declared media/ambiguous body | `structure_changed` or `incomplete_input`; never reinterpret as text-only/empty/unsupported type. |
| Size/count/duration budget, corrupt media, missing expected audio | Asset-specific limit/format/audio issue + incomplete coverage, not unrelated. |
| Timeout/disconnect/download/provider failure/cancel | Distinct execution status; preserve source/partial provenance, no successful cached verdict. |

### Files found and integration ownership

| Existing owner / file | Necessary proposed change |
| --- | --- |
| `backend/src/longtian_api/services/browser_operations.py:10` — atomic owner | Add enrichment exclusion with account/search/batch/open; retain paused ownership and challenge evidence page. |
| `backend/src/longtian_api/repositories/search_runs.py:467` — target/ordered terms; `services/search_runs.py:259` — admission | Factor canonical target projection. New screening service owns manual scope/revisions/reuse; preserve collection dedup/history/status. |
| `third_party/MediaCrawler/tools/auth_worker.py:174`, `:270`, `:346` — shared session/cancel | New typed dispatch, same cleanup; no backend crawler-global imports. |
| `third_party/MediaCrawler/tools/search_worker_protocol.py:18`; `backend/src/longtian_api/services/media_crawler_auth_worker.py:20` — IPC/64-KiB cap | Separate bounded enrichment protocol, metadata/handles and exact request/platform/content IDs. Preserve auth v2/search v1; no base64. Define UTF-8 budget; oversized full text uses validated normalized-manifest handle, not silent clipping/unbounded lines. |
| `third_party/MediaCrawler/tools/cdp_browser.py:81`, `:559`; XHS `product_search.py:796` — ownership/handoff | Reuse cleanup; never reclaim handed-off tab. Factor XHS navigation with unchanged-open regression. |
| Five `media_platform/<platform>/product_search.py`, cited parsers | New `product_enrichment.py` + shared selectors/downloader outside stores; minimum helper refactors. |
| Product DB/schema/services + runtime spool | Separate enrichment state; backend owns cloud config/prompt/payload. Public source/coverage/issues/progress only, no locators/paths. |

### Required fixtures and honest live gates

- Preserve `third_party/MediaCrawler/tests/test_product_search.py:255` tab sentinel and `:139` protocol; XHS open/handoff/no-fallback/fixed-source tests `tests/test_xhs_product_search.py:927`, `:983`, `:1082`; all five adapter suites and backend search worker/run/batch/connection suites. Synthetic search media proves **dropping**, not downloading (`tests/test_douyin_product_search.py:79`, `tests/test_kuaishou_product_search.py:158`).
- Platform fixtures: Toutiao body/images/video vs recommendations/ambiguity; Weibo long/clipped/missing/wrong-ID detail, picture shapes/new video; KS status/ID/progressive/H265/manifest/musicBlocked/image unknown; DY hit/miss/one-URL/mixed-gallery/audio-only/incomplete; XHS camel/snake/missing-url-default/wrong-ID/token/300031/ownership.
- Downloader fixtures: synthetic bytes; redirect/DNS/private-host/auth stripping; HTML-as-media; false/missing length/overflow; corrupt/huge media; audio presence/codec/HLS/blob/DRM; rendition/order; cancel/timeout/cleanup; traversal/symlink; encoded/aggregate inline limits. Assert no sentinel secrets/raw errors in IPC/API/logs/DB/provider payload.
- Cross-layer fixtures: whole durable scope not UI page; ownership/correlation; strict UTF-8/duplicate/extra/oversize frames; coverage/hash persistence; one browser owner; no calls on GET/startup/collection; retained source rows; manual refresh/reuse; no AI key in worker.
- **Live A:** for every claimed platform/type, approved stored public example proves exact ID, full text versus UI, ordered actual images/video bytes, MIME/duration/audio and honest partial/unsupported states. Search/open success is insufficient; untested cases remain unverified.
- **Live B:** user sentinel survives success/login/challenge/cancel/disconnect/shutdown; no block retry/bypass. Evidence only safe counts/types/outcomes, no tokens/terms/raw content/profile paths. Main coordinates later Centaurus sync/run/forwarding.
- **Live C:** approve cloud upload/quota and use backend-configured replacement key. Same model screens actual text/media; authorized clip has relevant spoken-but-not-visible meaning, image has meaning absent from caption. Prove grounding/coverage/uncertainty, not HTTP 200; reject text-only models honestly. No hosting/transcode/ASR workaround.
- **Live D:** bounded file lifecycle, explicit refresh, compatible reuse without paid recall, unchanged dedup/first-seen/history, no restart-triggered recrawl/upload.

### Related specs / external references / versions

- Read workflow/PRD and `.trellis/spec/backend/{product-search-guidelines,browser-search-adapter-guidelines,platform-connection-guidelines,auth-state-guidelines,batch-search-guidelines,error-handling,database-guidelines}.md`, shared reuse/cross-layer guides. No design/implement artifact at initial inspection. Borrowed-context exception does not authorize generic crawling.
- No browser/profile/runtime DB/platform/paid API access or tests/services/Git/rsync. Source endpoints are **not public API guarantees**. Inline-model option is main-agent research input, not live-tested here.
- `third_party/MediaCrawler/pyproject.toml:4`: declared 0.1.0, Python ≥3.11, httpx==0.28.1, Playwright ≥1.61.0, Pydantic ≥2.13.4, xhshow ≥0.2.0; not installed/commit verification. Source declares NON-COMMERCIAL LEARNING LICENSE 1.1; rights not audited.

## Caveats / Not Found

- No live proof: detail completeness/schema, CDN/expiry/redirects, type coverage, soundtrack and model audiovisual consumption require gates.
- No Toutiao detail/media, WB video or KS image-post extractor found. DY/XHS first-page lookup cannot promise arbitrary historic coverage.
- Filename/cover/page link/text connection test is not audiovisual proof. Unsupported/incomplete inputs stay visible, never silently unrelated/completed/summary evidence.
