# Research: Direct Code Fix for Content Enrichment

- Query: What direct product-code changes could make the current Weibo (`wb`),
  Kuaishou (`ks`), and Xiaohongshu (`xhs`) enrichment path produce truthful,
  analysis-ready inputs, and how should those changes be validated without live
  platform or model calls?
- Scope: internal
- Date: 2026-08-31

## Findings

### Observed acceptance boundary

The 2026-08-31 acceptance collected ten sources successfully but the independent
analysis job made zero model requests: all ten attempts settled as
`input_incomplete`; the sanitized record says nine exposed incomplete/unsafe media
inventory and one exposed a generic acquisition failure
(`verification.md:347-354`). The task evidence does not retain a per-result issue
matrix, so it is not possible to attribute the one acquisition failure to a
particular platform or code branch without reading runtime data or making another
call. Neither was in scope for this research.

The backend correctly distinguishes a completed enrichment transport from a usable
analysis input. `EnrichmentItem.ready` requires worker outcome `completed`, a
non-null content document, and `content.status == "ready"`
(`backend/src/longtian_api/services/content_enrichment.py:80-94`). The analysis
runner persists any non-ready content as `input_incomplete` and returns before
calling the model (`backend/src/longtian_api/services/content_analyses.py:255-295`).
`build_content_messages` rechecks the same boundary, the evidence fingerprint, all
media bytes, hashes and total size before encoding an AI request
(`backend/src/longtian_api/services/ai_analysis.py:203-285`). This separation is
deliberate and should remain.

### Exact ready blockers

#### Cross-platform readiness and media policy

`EnrichedContent` accepts `ready` only when all of the following are true:

- text coverage is `complete`;
- the platform claims a complete media inventory;
- there are no issues and no `unknown` modality;
- every declared image/video has one corresponding ready asset;
- every video is a self-contained supported MP4 with a proven audio track; and
- at least text or a verified asset exists.

The enforcing code is
`backend/src/longtian_api/services/enrichment_models.py:195-250`. The worker-side
materializer independently creates an issue for partial/unavailable text, any asset
failure, unknown inventory, caps, or empty evidence, and returns `partial` whenever
one remains (`third_party/MediaCrawler/tools/product_enrichment.py:139-280`). These
checks implement the current media-fidelity specification; they are not accidental
bugs.

The downloader's default host table contains no approved media host for `wb`, `ks`,
or `xhs` (`third_party/MediaCrawler/tools/product_media.py:36-44`). Consequently,
every locator from those adapters is rejected as `unsafe_media_url` before a
request. Adding guessed wildcard domains would be a regression: the downloader also
intentionally requires exact HTTPS hosts, no credentials/explicit port/fragment,
public DNS answers, no redirects, no ambient cookies/authentication, bounded bytes,
and a small MIME set (`third_party/MediaCrawler/tools/product_media.py:309-431`).
Local image/video probing then verifies format, dimensions, codecs and actual audio
(`third_party/MediaCrawler/tools/product_media.py:434-640`). This is deliberate SSRF,
credential-leakage, request-size, and evidence-integrity policy.

Other deliberate constraints that can continue to produce honest incomplete inputs
even after adapter work are: 6 MiB aggregate media, at most 24 images and one video
(`backend/src/longtian_api/services/enrichment_models.py:16-20,76-80`), no HLS/DASH,
no redirect following, no fallback to a cover, no second candidate after a failed
first download, and an audio-bearing H.264/HEVC MP4 requirement. These should not be
weakened incidentally while fixing adapter completeness.

#### Weibo

The Weibo snapshot deliberately keeps only `id`, `text`, `isLongText`, and `pics`
(`third_party/MediaCrawler/media_platform/weibo/product_enrichment.py:19-44`). Its
projector:

- marks long/unknown text as partial (`:57-71`);
- projects `pics` as image candidates (`:72-85`); and
- **always** returns `inventory_complete=False` because the projection cannot prove
  whether video exists (`:86-87`).

Therefore no Weibo source can become ready in the present adapter, including a
short, text-only post and a post whose images download successfully. The empty media
host allowlist is a second, independent blocker for posts with pictures. The tests
make this intentional current behavior explicit
(`third_party/MediaCrawler/tests/test_product_media_weibo.py:55-84,116-124`).

The upstream-derived crawler already has a detail-page full-text path
(`third_party/MediaCrawler/media_platform/weibo/client.py:258-278` and
`media_platform/weibo/core.py:533-586`), but it treats replacement detail data as
full text without the product adapter's strict proof. It also downloads images via
an unrelated third-party proxy and broad client behavior
(`media_platform/weibo/client.py:280-306`); that code does not satisfy the product
downloader contract and should not be reused wholesale.

A robust Weibo fix first needs a bounded minimal projection that proves all actual
post types: complete long text, pictures, and the presence or proven absence of a
video/card representation. Only then may the projector set
`inventory_complete=True`. The corresponding exact observed media hosts and any
required non-secret static Referer behavior need explicit fixtures and approval.

#### Kuaishou

The Kuaishou adapter makes one bounded exact-ID GraphQL detail request and extracts
caption plus progressive video candidates
(`third_party/MediaCrawler/media_platform/kuaishou/product_enrichment.py:26-45,113-152`).
However, the projector explicitly refuses to infer undocumented success semantics:

- any string caption is always `partial` (`:71-73`);
- media inventory is always false (`:93-100`); and
- every projection carries a top-level `structure_changed` issue (`:101`).

Thus Kuaishou can never become ready, even when its MP4 downloads and probes
successfully. The regression fixture asserts this exact condition
(`third_party/MediaCrawler/tests/test_product_media_kuaishou.py:52-60,124-165`). The
empty Kuaishou media-host allowlist is another independent blocker.

The broader upstream-derived GraphQL query contains more fields and its store treats
`photoUrl` as playable media
(`third_party/MediaCrawler/media_platform/kuaishou/graphql/video_detail.graphql:1-79`,
`third_party/MediaCrawler/store/kuaishou/__init__.py:55-79`), but neither proves the
meaning of `status`, `type`, caption completeness, exhaustive media inventory, or
safe hosts. The direct fix must establish those semantics from bounded exact-ID
fixtures before removing the hard-coded partial flags. Merely changing
`status == 1` to ready would contradict the current documented safety decision.

#### Xiaohongshu

Xiaohongshu is closest to a working strict adapter. A normal note with complete
title/description, a verified image list, and proven absent video can be ready; a
verified empty image list can be text-only ready
(`third_party/MediaCrawler/media_platform/xhs/product_enrichment.py:98-163`,
`third_party/MediaCrawler/tests/test_product_media_xhs.py:51-106`). Video notes
retain one actual H.264 stream candidate rather than substituting a cover
(`product_enrichment.py:136-160`).

For image/video posts, the empty XHS media-host allowlist makes otherwise valid
locators fail as `unsafe_media_url`. Adding exact observed hosts, with the existing
downloader guards intact, is the smallest adapter slice likely to turn ordinary XHS
image notes ready.

A separate reliability risk is token reacquisition. The saved canonical result does
not retain the private XHS search token. Enrichment performs a fresh first-page
search using the original matched term, then fails `lookup_miss` if the exact note
is no longer in that page (`product_enrichment.py:183-251`, especially `:217-227`).
This is a plausible source of a generic acquisition failure, but the sanitized
acceptance evidence does not prove it was the cause this time. Host approval alone
does not fix stale/reordered XHS search results. A durable design must either perform
enrichment while an ephemeral token is still owned, define an equally bounded
reacquisition contract, or explicitly accept this historical-source limitation; it
must not persist or log the token casually.

### Safety policy versus incomplete implementation

| Behavior | Classification | Direct-fix implication |
| --- | --- | --- |
| Exact source identity, minimized projections, no raw page/profile/token persistence | Deliberate safety/privacy policy | Preserve; extend only minimal proven fields. |
| Unknown inventory cannot be labelled text-only ready | Deliberate evidence-fidelity policy | Preserve under strict mode; a fallback is a separate product decision. |
| Exact CDN hosts, public-DNS pinning, no auth/cookies, redirects, playlists or arbitrary MIME | Deliberate transport policy | Add only observed exact hosts and fixed safe headers; do not add wildcards or generic downloading. |
| Byte/hash/MIME/dimension/codec/audio checks and private operation-scoped staging | Deliberate integrity policy | Reuse unchanged. |
| Weibo always reports unknown inventory | Incomplete adapter backed by an honest safety default | Extend detail projection so absence/presence of all media types can be proven. |
| Kuaishou always marks caption partial, inventory unknown and `structure_changed` | Incomplete adapter backed by an honest safety default | Establish exact response semantics, then remove only those conservative sentinels justified by fixtures. |
| WB/KS/XHS media host sets are empty | Explicit unimplemented live-acceptance gate | Populate only after observed-host acceptance and adversarial fake tests. |
| XHS re-searches first page to recover a token | Deliberate privacy choice with a reliability gap | Redesign separately if historical/reordered results must enrich reliably. |

### Smallest robust implementation slices

These slices are independently testable; the ordering avoids weakening the safety
boundary just to produce a green end-to-end run.

1. **Characterization tests first.** Freeze the currently supported response shapes,
   readiness outcomes, and `unsafe_media_url` behavior for all three platforms. Add
   negative cases for malformed aliases, missing inventory, mixed media types,
   private DNS, redirects, cookies/auth, MIME mismatch and caps before changing
   semantics.
2. **Exact-host media transport slice.** Add only sanitized, observed CDN hostnames
   to `VERIFIED_MEDIA_HOSTS`, with a table-driven test per platform proving accepted
   exact hosts and rejecting suffix confusion, hostname case variants, ports,
   credentials, redirects and private DNS. If a platform requires a Referer, allow
   only a fixed platform/canonical-source value; never forward browser cookies or
   signed source locators as headers. This slice alone can help XHS, but cannot make
   WB/KS ready.
3. **XHS normal-note slice.** Validate complete image-note materialization end to end
   with fake network bytes and a fake browser snapshot. Keep malformed/mixed video
   representations non-ready. Treat video and token-reacquisition reliability as
   separate follow-ups.
4. **Weibo source-semantics slice.** Extend the browser-side minimized snapshot and
   pure projector to prove complete long text and exhaustive post media/no-media
   state. Do not expose whole `page_info`, authors, reposts, interaction data, or
   signed locators in persisted evidence. Add synthetic JavaScript-in-Chromium tests
   so lossy projection bugs cannot hide behind Python fixtures.
5. **Kuaishou source-semantics slice.** Establish status/type/caption/inventory
   semantics from exact-ID response fixtures, then allow one proven progressive
   source asset to be complete. Preserve unsupported manifest/cover-only and mixed
   or unknown shapes as partial. Test both H.264 and HEVC candidates against the
   existing codec/audio probe.
6. **Only then integrate backend-to-report fakes.** Feed the worker result through
   `ContentEnrichmentService`, independent analysis, the fixed automation wait, and
   topic-report admission. Assert a valid item calls the fake model exactly once,
   incomplete items never call it, staged bytes are deleted, saved evidence omits
   handles/URLs, and report source membership reconciles.

Estimated relative effort and uncertainty:

| Platform/slice | Effort | Main uncertainty |
| --- | --- | --- |
| XHS normal text/image | Small–medium after an approved host fixture exists | CDN host variation and signed URL expiry. |
| XHS video | Medium–large | MP4 size/codec/audio limits and token reacquisition. |
| Weibo text-only/image | Medium–large | Proving exhaustive mixed-media/no-media state and full long text. |
| Weibo video/card | Large | Minimal trustworthy page schema and supported actual media locator. |
| Kuaishou video | Medium–large | Undocumented status/type semantics, CDN variation and videos over 6 MiB. |
| Backend strict path | Small | Mostly already implemented; preserve contracts and add integration coverage. |
| Text-only graceful degradation | Medium–large cross-layer feature | New product semantics, durable evidence/report labelling, reuse/fingerprint compatibility. |

### Strict full multimodal completion versus text-only degradation

The two behaviors solve different problems and should not be conflated.

**Strict full completion** is the current contract. It sends an item to the model
only after every detected original modality is present and verified. Its benefit is
that the resulting understanding can truthfully claim it considered the whole
available post. Its cost is low availability: one expired image, oversized video,
unknown media inventory or missing audio blocks the entire item. Direct adapter and
host fixes should retain this behavior unless the product requirement changes.

**Text-only graceful degradation** can increase report coverage for sources with
complete meaningful text but unavailable media. It is not a content-completion fix;
it is a new analysis mode. A safe implementation must not relabel partial enrichment
as `ready`, because the durable report schema also revalidates `status == "ready"`,
complete inventory and zero issues
(`backend/src/longtian_api/schemas/topic_report_engine.py:128-148`). Instead it would
need an explicit durable mode/coverage contract (for example `full` versus
`text_only`), separate eligibility rules, prompt wording that states media was not
reviewed, preserved acquisition issues, compatible fingerprint/reuse rules, and UI/
report disclosure. Complete nonblank text would be the minimum; title-only,
partial/unavailable text, and video-only sources should remain blocked unless the
user chooses different evidence rules.

Choosing between strict-only and adding a text-only mode changes what the report
means and is therefore user-owned product behavior. The implementation should not
silently achieve throughput by weakening `EnrichedContent.ready`.

### Fake-first validation strategy

No live platform or model work is needed until these layers pass:

1. **Pure projection tables:** exact positive/negative dict shapes for each adapter;
   assert text coverage, inventory completeness, candidates and issue codes.
2. **Actual JavaScript projection:** execute each snapshot script in
   network-disabled Chromium, then run the Python projector. Include malformed,
   absent, mixed, over-limit, wrong-ID and private-field sentinels. This is required
   by `.trellis/spec/backend/media-projection-guidelines.md`.
3. **Transport fakes:** use `httpx.MockTransport` plus fake public/private resolvers;
   test exact host acceptance, DNS pinning, zero cookies/auth, redirect rejection,
   response caps, MIME mismatch, signed-query preservation and cleanup.
4. **Media probe fixtures:** small valid JPEG/PNG/WebP and self-contained MP4
   fixtures; reject malformed bytes, unsupported codecs, no audio, oversized media,
   and mismatched declared metadata. Keep `ffprobe` local-only.
5. **Worker/protocol boundary:** fake browser context and staged files through
   `tools/auth_worker.py`; verify one terminal event, manifest fallback, cancel/
   disconnect cleanup, and no raw locator/token in the event.
6. **Backend acquisition:** existing fake worker through
   `backend/tests/test_content_enrichment.py` and
   `backend/tests/test_enrichment_staging.py`; prove ready/partial outcomes, hashes,
   private file ownership and cleanup.
7. **Analysis/report integration:** fake AI only, asserting zero calls for incomplete
   input and exactly one call for ready input; then verify automation waits for the
   nested job and admits a report only after settlement. Useful suites include
   `backend/tests/test_content_analyses.py`, `test_topic_report_smoke.py`, and
   `test_automation_workflows.py`.
8. **Bounded live acceptance last:** after all fakes pass and the user approves,
   observe at most one fresh source shape/host per platform, stop for login/challenge/
   rate-limit/manual action, sanitize only structural facts, and amend exact host/
   shape fixtures before a small end-to-end retry. A live URL must never be copied
   directly into a committed fixture.

Suggested focused commands for an implement/check phase are:

```text
cd third_party/MediaCrawler
uv run pytest tests/test_product_media_projection.py tests/test_product_media_io.py \
  tests/test_product_media_weibo.py tests/test_product_media_kuaishou.py \
  tests/test_product_media_xhs.py tests/test_product_media_worker.py \
  tests/test_product_media_protocol.py

cd backend
uv run pytest tests/test_content_enrichment.py tests/test_enrichment_staging.py \
  tests/test_content_analyses.py tests/test_topic_report_smoke.py \
  tests/test_automation_workflows.py
uv run ruff check .
uv run ruff format --check .
```

Full backend and derivative suites remain required before live acceptance; focused
tests are not a substitute.

### Files found

- `backend/src/longtian_api/services/enrichment_models.py` — strict enrichment
  schema, readiness invariant, source validation, budgets and fingerprints.
- `backend/src/longtian_api/services/content_enrichment.py` — serial browser owner,
  worker validation, staged-media transfer and `EnrichmentItem.ready`.
- `backend/src/longtian_api/services/enrichment_staging.py` — private descriptor-
  relative staging, byte/hash/media verification and narrow cleanup.
- `backend/src/longtian_api/services/content_analyses.py` — input acquisition and
  the no-model-call path for incomplete content.
- `backend/src/longtian_api/services/ai_analysis.py` — final in-memory content/media
  revalidation and multimodal request construction.
- `backend/src/longtian_api/schemas/analysis_evidence.py` — durable saved input with
  no blob handles, paths, locators or bytes.
- `backend/src/longtian_api/schemas/topic_report_engine.py` — downstream strict-ready
  evidence revalidation.
- `third_party/MediaCrawler/tools/product_enrichment.py` — shared projection
  materialization and fixed-origin bounded client.
- `third_party/MediaCrawler/tools/product_media.py` — exact host table, DNS-pinned
  downloader, media staging and local probe.
- `third_party/MediaCrawler/tools/auth_worker.py` — borrowed-Chrome enrichment
  dispatch and operation ownership.
- `third_party/MediaCrawler/media_platform/{weibo,kuaishou,xhs}/product_enrichment.py`
  — current exact-source platform adapters.
- `third_party/MediaCrawler/tests/test_product_media_{projection,io,weibo,kuaishou,xhs,worker,protocol}.py`
  — existing fake-first and offline-browser coverage.
- `backend/tests/test_content_enrichment.py`, `test_enrichment_staging.py`,
  `test_content_analyses.py`, `test_topic_report_smoke.py` — backend cross-layer
  fixtures and lifecycle tests.
- `third_party/MediaCrawler/LICENSE` — dependency permits modification/merging only
  for non-commercial learning/research and prohibits large-scale/disruptive crawling.
  Product deployment intent must be checked separately before relying on the fork.

### Related specs

- `.trellis/spec/backend/media-projection-guidelines.md` — unknown inventory,
  actual-media and JavaScript-projection fidelity contract.
- `.trellis/spec/backend/initial-analysis-guidelines.md` — saved input, lifecycle,
  URL/privacy, fake-browser/fake-provider validation and independent analysis rules.
- `.trellis/spec/backend/ai-summary-guidelines.md` — shared multimodal transport,
  privacy and usage requirements referenced by initial analysis.
- `.trellis/spec/backend/product-search-guidelines.md` — canonical stored search
  identities and borrowed-Chrome ownership.
- `.trellis/spec/backend/automation-workflow-guidelines.md` — fixed collection to
  analysis to report orchestration and retry behavior.
- `.trellis/spec/infra/submodule-guidelines.md` — derivative changes must be
  committed/pushed in the submodule before the parent gitlink moves.

## External References

No web or GitHub search was performed for this direct-code route; the separate
library-reuse research owns that comparison. The only third-party material inspected
was the repository-pinned MediaCrawler derivative and its local license/source.

## Caveats / Not Found

- This research made no platform, browser, runtime database, or model call and did
  not inspect signed media URLs. Therefore it does not propose actual WB/KS/XHS CDN
  hostnames; guessing them would violate the current acceptance gate.
- The sanitized acceptance record does not map each of the ten results to exact
  issue codes, so the single acquisition failure cannot be attributed with certainty.
- Task artifacts state that pre-existing product/submodule changes were preserved.
  They specifically mention unrelated API-key-mask and rule-placeholder frontend
  edits (`research/rule-cleanup-verification.md:75-76`) and otherwise leave submodule
  changes unspecified (`verification.md:238-251`). This research role forbids Git
  operations, so it did not independently enumerate the dirty diff. An implementer
  must resolve ownership before editing the same submodule files and must not revert
  unrelated changes.
- The current task PRD originally classified product/submodule code changes as out
  of scope, then added only the analysis-wait fix authorization. A new enrichment
  implementation requires a planning/authorization addendum before code changes.
- Text-only graceful degradation changes report semantics and durable contracts; it
  should be decided explicitly rather than smuggled into an adapter readiness fix.
- The pinned MediaCrawler license is non-commercial-learning-only. This research
  does not determine whether the intended use is compatible or whether separate
  permission is needed.
