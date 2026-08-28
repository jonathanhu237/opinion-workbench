# Exact-source browser observations — 2026-08-28

The user approved opening a few already collected originals in the current Chrome
browser. This is a **DOM/player research gate**, not production byte-transfer or AI
acceptance. No model request, database mutation, profile/storage read, or generic
detail/search request was made.

## Douyin: stored source 372

One agent-owned tab navigated once to its stored canonical video URL. The page
rendered normally after its visible loading message disappeared; there was no
login/challenge. Two pre-existing user tabs were not changed.

- Exactly one `[data-e2e="detail-video-info"][data-e2e-aweme-id="<stored id>"]`
  contained exactly one `h1`. Its bounded caption agreed with the screenshot.
- An `展开` button exists inside that information region, but the browser locator
  reported it **not visible** for this short caption. Do not assume that every
  caption is complete merely because an `h1` exists. A visible expand control or
  clipped/ambiguous caption must remain incomplete until explicitly handled.
  It is a native `button`, not a text-only span; scoped `get_by_role("button",
  name="展开", exact=True)` matched it. Its hashed classes are not a stable contract.
- Exactly one `[data-e2e="player-container"].video_<stored id>` contained exactly
  one `xg-video-container video`. Another empty/hidden video existed elsewhere;
  page-wide video selection would be unsafe.
- The content player's actual `currentSrc` was HTTPS on the exact host
  `v26-weba.douyinvod.com`, also present as a video in the browser's page-assets
  inventory. The full signed locator was kept only in browser-session memory.
- The player reported 15.1 seconds and 576 × 1024. These are **player metadata**,
  not independent MP4/audio validation. No poster was observed; four `source`
  children were alternate sources, not four works.
- Browser evaluation's geometry properties returned zeros even for visible
  content. They are not valid live clipping evidence; use the actual screenshot
  and supported visibility locator for this audit. Production geometry checks
  require real offline DOM fixtures.

## Narrow implementation boundary

Replace only the explicit Douyin `structure_changed` seam with an exact-ID,
bounded canonical-page projection. The expected files are its
`media_platform/douyin/product_enrichment.py`, a dedicated synthetic test module,
and the exact-host entry in `tools/product_media.py`. Reuse existing owned-page,
navigation, materialization and validation helpers. Preserve every other dirty
file. No state/API/signature fallback, recommended-feed extraction, hidden-video
selection, cover substitution, URL fabrication, browser-level scripts, or retry.

The observed host may be tried once by the existing bounded public downloader;
adding it does not bypass byte/MIME/hash/audio validation and does not establish
any other CDN subdomain. Unknown hosts remain denied. A real supported-media
gate and later independent review are still required.

## Toutiao: stored source 143

The same owned tab navigated once to the exact stored legacy HTTP `/a<id>/` URL.
The browser ended at HTTPS `www.toutiao.com/article/<same id>/` with no login or
challenge. This proves that legacy stored source needs compatibility, not that
arbitrary HTTP sources should be accepted. Do not rewrite the stored row.

- Exactly one `article.syl-page-article.tt-article-content` inside
  `div.article-content` contained 21 paragraphs and 1,629 body characters.
- Its enclosing `div.article-content` had the native `h1` (30 characters). The
  accessibility `main` is not a native `main` element: `main h1` found zero.
- No expand/full-text/next-page link was found inside the article. The end-of-
  article `举报` control was rendered and visible to its supported locator. The
  article is separate from comments, author information and recommendations.
- Eight `img.syl-page-img` elements were each in `div.pgc-img`, **not** inside
  the video box. Every one had a `data-src` HTTPS locator on the exact host
  `p3-sign.toutiaoimg.com`. One was loaded at 1920 × 1080; the other seven had
  one-pixel data-URL placeholders and `syl-img-loading`. A placeholder `src`
  must not be downloaded or counted as the actual image; use the observed
  `data-src` candidate, subject to ordinary byte/MIME validation.
- One actual `video` lived in `.tt-video-box.syl-page-video` inside the article.
  Its `currentSrc` was HTTPS on `v3-web.toutiaovod.com`; player metadata reported
  197.52 seconds and 1920 × 1080. Screenshot confirmed the embedded video. This
  is an article containing both video and images, not a text-only article.
- No `picture` or `iframe` was observed inside this sample. Other article shapes,
  lazy inventory completion and video/micro-post routes remain unverified.

### Toutiao compatibility and implementation boundary

Implement only the observed article DOM path. Keep unknown/micro-post/video-only
layouts explicitly unsupported/incomplete. The adapter, dedicated tests and two
exact media-host entries are the platform code boundary.

In the paired enrichment source validators, allow only the known stored legacy
`http://www.toutiao.com/a<numeric stored id>/` form (optional single trailing slash),
with no query/fragment/credentials/port. The adapter must upgrade its scheme to
HTTPS **before** its single navigation; normal same-ID official redirect may then
select the article route. The normalized result retains the exact stored URL for
identity correlation. Other HTTP forms remain invalid. Update shared fixtures and
wire-contract note; no search behavior, database migration or public API changes.

Main assigns this minimal paired-compatibility/TT work to the backend implementer;
the fork implementer retains DY. Shared host-map editing is sequenced through the
fork implementer/main to prevent overlapping edits. Actual byte/audio and safe
handoff gates remain separate and have not passed on these DOM observations.

### Additional end-of-body observation

A second, explicit inspection of the already observed HTTPS article URL verified
the report control's location (not a failed-request retry). It is
`div.detail-report[role="button"]` with exact `举报` text, inside `div.action`,
outside `article` and `.article-content`. The shared ancestor is `div.main`, in
`div.article-detail-container[role="main"]`. That `.main` contained exactly one
article and one `.article-content`; its direct children were `.show-monitor`,
`.action`, then an unclassified div. `.article-content` children were `h1`,
`.article-meta`, and an unclassified wrapper containing the article. A global
report button is not sufficient end-of-body proof.

## Kuaishou: stored source 353

One canonical navigation rendered the source caption and one video in
`.kwai-player-container-video`. Initial video metadata was empty. Clicking the
visible play control on the owned page started playback; no login/challenge or
navigation retry occurred. `currentSrc` was HTTPS on the exact observed host
`k0u2ay30y79ya8zw2408x8752x0x101xx28z.djvod.ndcimgs.com`; player metadata was
73.899333 seconds and 720 × 1280. No media bytes were downloaded by the production
probe. This DOM observation does **not** establish the existing candidate GraphQL
status/body completeness semantics or arbitrary CDN subdomains.

## Weibo: stored source 173

One exact mobile-detail navigation rendered the original text and a post image.
The content image was `img.f-bg-img` inside `.m-img-box.m-imghold-4-3`, loaded at
360 × 270 on `ww2.sinaimg.cn`. Separate avatar/icon hosts were excluded. A page-
level video existed inside `.mwb-video`, but had no source/duration; its mere
existence is not evidence of source video or proof of media absence. No production
media download or full inventory acceptance was performed for this source.

## Xiaohongshu: stored image source 492

One direct stored canonical navigation reached the official unavailable page with
code `300031` and message `当前笔记暂时无法浏览`. There was no challenge automation,
reload, alternative source or token/state inspection. This source visit is
unavailable, **not** a platform-wide failure or proof of deletion. The product's
separately specified bounded first-page/exact-ID reopening path was not exercised.

## Actual file-only checks

`verification/live_asset_probe.py` takes one already observed locator via private
stdin and calls the production `MediaDownloader`, `MediaStaging` and `MediaProbe`.
It has no browser/controller, database, provider client, raw-error logging, URL
argv or persistent locator manifest. Exact production host allowlists and the
6 MiB/time/MIME/hash guards remain enabled. Source was copied to Centaurus and an
unsafe-loopback-input rejection/cleanup check ran there before live checks.

The local real-input check used the existing trusted ffprobe8.1.2 executable and
the local network path of the user's approved browser session. This is a bounded
file probe, not a resource-intensive suite, media conversion or remote transfer.

| Observed asset | Result | Actual bytes | File metadata | Cleanup |
| --- | --- | ---: | --- | --- |
| DY source372 video | ready | 4,432,193 | MP4,576×1024,15,100ms,audio present | operation empty; temporary root removed |
| TT source143 first actual image | ready | 568,274 | JPEG,1920×1080 | operation empty; temporary root removed |

No files or raw locators were retained. The TT article has additional images and
an embedded video: this single-image check is not complete-source acceptance.
These checks prove production file I/O/probing on actual assets, **not** the whole
extractor→worker→backend handoff, browser cancellation/sentinel live gate, model
input or five-platform support. No AI request was made.

## Browser cleanup observation

Main explicitly closed only the newly created audit tab. At the final read-only
snapshot **before** that close, one of the two baseline tab IDs was already absent;
the other remained. A read-only user-tab listing also did not contain the absent
ID. No main-session navigation/close targeted either baseline tab, but its absence
has no observed cause. Do not assert that a two-tab live sentinel gate passed or
reopen a tab the user may have deliberately closed. The owned audit tab was absent
after its explicit close. Product cancellation/disconnect/sentinel testing remains
separate from this manual research visit.
