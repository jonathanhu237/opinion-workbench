# Douyin media repair boundary — 2026-08-28

The user explicitly approved fixing Douyin media acquisition after the two real
summary attempts documented in `verification.md`. This is a narrow dependency
repair under the active summary task. It supersedes the original integration
slice's prohibition on fork edits only for the files and behavior below.

## Gap and evidence

Run 41's summaries 1 and 2 made zero provider requests. Summary 2's five sources
were input-incomplete; source 124 saved a partial caption and missing video,
while the other four had no normalized input. Their approximately 11-second
durations match the adapter's 10-second structural wait, but do not prove the
precise worker failure for each item. A later exact-source browser visit to 124
rendered a visible full caption/player and played normally. The observed media
host was `v95-web-sz.douyinvod.com`, not the sole currently permitted host.

The adapter currently accepts structural readiness before visibility/currentSrc
readiness, swallows a readiness timeout, and immediately takes a single snapshot.
Fix premature classification with bounded, cancellable, source-specific readiness
and evidence-backed exact-host compatibility. Do not assume an absent snapshot
means a login failure, deleted post, or unrelated content.

## Ownership and expected changes

- `third_party/MediaCrawler/media_platform/douyin/product_enrichment.py`: owns the
  exact-ID page readiness and complete-caption/player projection. Reproduce the
  readiness failure in a network-disabled real DOM fixture before changing it.
- `third_party/MediaCrawler/tools/product_media.py`: add only the observed exact
  Douyin CDN hostname if the existing public-address/TLS/redirect/file guards stay
  intact. Do not allow arbitrary subdomains.
- The derivative's existing Douyin/media test modules: delayed rendering, visible
  source versus hidden/recommended player, incomplete captions, missing source,
  timeout/cancellation and exact-host positive/negative regressions.
- Main owns task/spec records, source-only remote synchronization, live checks,
  normal local backend restart if needed, and user-facing result reporting.

Shared worker/protocol, browser ownership, backend/UI/schema and other platform
changes are not assumed necessary. If diagnosis proves a necessary additional
file, report the exact behavior gap before widening the repair.

## Preserved boundaries

No copied browser profile, hidden application state, cookies, new detail API,
signature bypass, CAPTCHA handling, source substitution, recommended-feed scan,
cover-only/text-only fallback, media conversion, cloud upload API or new provider.
Keep current complete-input validation, 6 MiB raw / 9,000,000-byte request caps,
20,000-character text limit, actual MP4/audio verification and owned cleanup.
Keep one navigation per acquired source; waiting for rendering is not a reload
or download retry. Do not activate an unrelated browser tab or change user
browser settings. No automatic summary request, commit, push or archive.

## Additional exact-source observations

The main agent's one-navigation browser inspection subsequently found that stored
`/video/<id>` URLs for results 125, 121, 122 and 123 redirect to `/note/<same-id>`.
Their primary content is an image post, not a video detail (125 displayed 1/3,
122 displayed 2/5, 123 displayed 2/3). This is a separate unsupported-layout cause, not evidence
that a longer video readiness wait will fix those items. Keep exact source/type
validation and do not consume a recommended video from these pages. The current
repair targets video acquisition; image-post support remains unverified.

Source 124 had no detail/player at the first 0.9-second observation and a visible
caption/player at the next 15.1-second observation. These two observations alone
do not establish the exact readiness time or prove a delay exceeding 10 seconds.
The network-disabled real-DOM regressions independently reproduce premature
projection when structure exists before visibility or `currentSrc` readiness.

### Remaining caption-box gap after summary 4

The user-approved continuation reached actual complete MP4 acquisition, but
source 124 was still partial solely because of `text_incomplete`. Main's fresh
exact-source screenshot/DOM inspection showed complete two-line caption text
inside the clipping parent's bounds. The inline `h1` had zero client/scroll
dimensions, `font-size:32px; line-height:0px`, and a 71px element box; its actual
descendant text ranges were two 25px lines wholly inside the 52px parent.
The parent's scrollHeight was 57px because of box overflow, not hidden text.

The same adapter/test-file ownership now includes correcting this false partial
classification with actual text-layout evidence. Reproduce the inline/descendant
font case in network-disabled Chromium first. Do not waive unknown geometry,
hidden/cropped nonempty text, visible expansion, real overflowing ranges or
ellipsis. No new media modality, source, endpoint, layout mutation or model call
is authorized merely by this correction; the original finite live-call bound
and independent check still apply.

The observed caption-to-info chain has zero padding/borders, `box-sizing:
border-box`, no CSS transform/translate/rotate/scale, and zoom 1. The bounded
correction may compare nonempty text-node Range rectangles against actual clip
ancestors in this supported layout; complex/unverifiable geometry must remain
unknown. Do not introduce a fixed 5px overflow exemption. The main-owned audit
tab was closed after these read-only measurements.

The implementer reproduced two network-disabled real Chromium failures before
changing production: a 32px inline heading with zero line-height/client metrics,
and a 64px glyph-overflow variant whose actual text ranges still fit the 52px
clip. Both old projections returned unknown clipping and failed the expected
complete-caption assertion (**2 failed**, 1.95s). The fixture is semantic, not
dependent on reproducing Mac font pixels or mocked DOM geometry.

## Validation

### Remaining line-clamp gap after summary 5

Summary 5 again acquired complete video but no complete text or model result.
After restoring the supported Browser connection, main inspected the same source
without changing layout. The full caption-to-HTML ancestor chain and nonempty
text descendants had no additional transforms, masks, filters, containment or
nonzero borders. Two nonempty text nodes (5 and 57 characters) had three positive
text rectangles fully inside all clipping ancestors. The only zero-width span
was empty; expansion was not visible and the caption had no trailing ellipsis.

The discriminating observation is the direct caption parent's actual computed
`-webkit-line-clamp: 2`, `-webkit-box-orient: vertical`, `display: flow-root`,
52px height and hidden overflow. Reading the hyphenated property with
`getPropertyValue` exposed this value; the inspection tool's camel-case style
property returned an empty string and was not evidence of absence. Production's
native style check rejects any configured clamp, including this complete
two-line caption.

The [CSS Overflow draft's legacy compatibility rules](https://drafts.csswg.org/css-overflow-4/#continue)
explain why a clamping legacy box can compute to `flow-root`; that display value
is not an exemption. The same adapter/test ownership now covers a regression
that distinguishes a configured two-line maximum from actual text omission.
Keep real clamping and unverifiable geometry incomplete; do not simply remove
the clamp guard, mutate CSS or infer completeness from scroll height. First
prove the distinction in network-disabled Chromium, then independently check
the bounded implementation before another same-scope live operation.

The implementer's initial six-case real Chromium experiment returned **2 failed /
4 passed** (4.12s): complete two-line captions failed the old unconditional clamp
guard. Importantly, a genuinely clamped third line can still have positive Range
rectangles inside an explicitly enlarged 130px container. Comparing only outer
clip bounds cannot prove completeness. Any narrow fix must also establish the
caption's full line extent against the clamp, keeping that oversized-container
counterexample incomplete. This is red-test evidence, not a completed repair.

Additional main-owned read-only checks confirmed 61 non-whitespace Unicode
characters each have positive geometry inside the direct clip; none were missing
or outside. Actual text spans/links use 18px font, 26px line height, baseline
vertical alignment and no floats. Their positions are static, except one relative
link with all four insets 0px; the clipping DIV is also relative with 0px insets.
The inline H1 has 32px font, zero line height and default 21.44px vertical margins,
which do not establish the actual descendant text's line height. No page mutation
or additional source navigation was used to obtain these measurements.
The direct clip's two child nodes are a `display: none` DIV wrapping the expand
button and the inline H1; there are no text-node siblings. This supports limiting
the clamp proof to the exact H1's direct container, rather than trying to infer
line consumption in unrelated ancestor/sibling content.
Applying the proposed row-slot formula read-only on this source found one 26px
text line height, rows 0 and 1, and zero invalid character rectangles. The
clipping DIV's `::before` is an empty-string, transparent, zero-width right float
of height 27px; its `::after` and all caption/descendant before/after content are
`none`. A blanket ban on every pseudo-element would reject the same real layout
again. This metadata is not itself a complete production-worker check.

The implementer's intermediate post-fix gate passed 149 Douyin tests with zero
skips (45.49s), including the six-case core matrix. Independent static review
then held the gate for a concrete generated-content counterexample: a
zero-height block `::before` containing text consumes a clamp line even though
the caption's character ranges fit the apparent two-row area. A real Chromium
red regression reproduced false completeness (**1 failed**, 1.53s), with
clamped/unclamped screenshots differing inside an oversized container. The
same bounded fix must cover generated layout on empty inline descendants while
preserving the actual empty zero-width float. No production acceptance or model
success is claimed from this intermediate test count.

1. Implementer demonstrates a failing regression and a bounded fix using real
   network-disabled Chromium DOM fixtures; tests and builds run on Centaurus.
   Local source/Git remain authoritative; never copy runtime, media or credentials.
2. Required independent Trellis check covers the changed derivative scope, existing
   media/worker tests and parent integration contracts. Use the maintained
   derivative `tests/` suite, not legacy root modules requiring external services.
3. Main verifies the normal local application with the same five results in run
   41 and unchanged saved configuration revision 1. At most five new item calls
   plus one text-composition call; skip incomplete sources truthfully. No extra
   history, private probe cache import or repeated paid debugging attempts.
4. Record actual source coverage, acquired metadata, report citations and validated
   usage. A terminal empty template is not successful model/report acceptance.

## Bug Analysis: premature video acquisition

### 1. Root Cause Category

- **D — Test Coverage Gap**: static projection fixtures did not exercise a real
  page whose structure appeared before visible text/player or media source.
- **E — Implicit Assumption**: structural presence was treated as readiness, and
  the sole previously observed CDN hostname did not cover this player's host.
  Separately, stored video-shaped links were not proof of video source type.
- **E/D — Caption geometry**: zero client dimensions were assumed invalid even
  for an inline heading, and overflowing font boxes were assumed to mean hidden
  text. Earlier real-DOM fixtures still used ordinary heading layout, missing
the actual large-inline-heading/smaller-descendant-text case.

### 2. Why earlier attempts did not establish success

The two summary attempts were live checks, not verified code fixes. Both settled
with zero model calls. A later usable page or a terminal empty report could not
prove that the original worker had acquired complete input.

Summary 4 proved the readiness/CDN repair worked for actual media, but exposed
the independent caption-geometry gap. A successful focused regression or media
download was therefore insufficient to declare full item-input readiness.

### 3. Prevention mechanisms

- Runtime: one cancellable readiness budget; strict source/type and challenge
  checks during waiting; a fresh final snapshot with no completeness promotion.
- Tests: real network-disabled DOM transitions, permanent partial/unknown cases,
  cancellation, same-ID note redirects, and equal guards on both exact hosts.
- Spec: `backend/media-projection-guidelines.md` now requires those contracts and
  regressions. This application has no `src/templates/markdown/spec/` mirror.

### 4. Systematic expansion

Other platform adapters may have timing or layout gaps, but this finding does not
authorize changing them or declaring them ready. Image-post support is a separate
known gap. Independent review and a real full application run remain necessary;
a unit fixture or successful file download cannot replace either.

### 5. Knowledge capture

Evidence and boundaries are retained here and in `verification.md`; executable
contracts are in the media-projection spec. Git changes remain uncommitted until
the user requests the normal commit/push workflow.

## Final checkpoint — 2026-08-28

The generated-content regression and harmless zero-width-float case are now
resolved within the same bounded caption proof. The final focused Douyin gate
passed **160 tests / zero skips**; independent review passed **1,126 maintained
derivative tests / zero skips**, with scoped lint/format and frozen local/remote
hashes matching. Earlier intermediate counts and blockers above are historical,
not the final acceptance result.

The normal local application then completed **summary 6** for the same five
run-41 sources and unchanged saved model configuration. Source 124 supplied its
complete caption and actual video with audio, received one Qwen analysis, and
was cited in the generated text-only report. Total verified usage was **2 model
requests / 13,518 tokens**. The four image-post redirects remained explicitly
incomplete and did not call the model. Request-UUID replay was verified without
new work; cross-generation paid reuse was not exercised. Complete metadata,
token breakdown, attribution cautions and spool cleanup are in
`verification.md` under “Final live acceptance”.

This closes the narrow repair's real application/model acceptance, not the
separate image-post support gap or all-platform media acceptance. No user
credentials, runtime, media or database were transferred for testing, and no
commit, push or archive was performed in this continuation.
