# Media Projection Fidelity

## 1. Scope / Trigger

Use when minimizing a platform source before full-text/media acquisition. This
covers internal enrichment projections, not authorization to read browser storage,
new endpoints, or a claim of live platform support. Preserve proven absence,
malformed/unknown inventory, inaccessible assets and actual complete input.

## 2. Signatures

The derivative owns source-specific projection and normalized materialization:

```python
project_note(value: object, content_id: str) -> SourceProjection
project_detail(value: object, content_id: str) -> SourceProjection
materialize(command, projection, staging, downloader, probe) -> dict
```

`SourceProjection` has `title`, `body`, `text_coverage`, `inventory_complete`,
ordered `assets` and `issues`. Backend content validation is independent. This
rule adds no public API, environment key or database field.

## 3. Contracts

- Validate the original shape and the minimized projection. A strict Python parser
  cannot recover information already discarded by JavaScript.
- Null/absence can mean no video only for a verified source representation. Present
  strings, booleans, arrays or numbers must not be converted into absence.
- Keep malformed list entries unknown or fail explicitly. Do not wrap an invalid
  stream in an ordinary object and then declare all stream entries structurally valid.
- Unknown sentinels are constant and minimal: never preserve whole source objects,
  tokens or private fields merely to retain shape information.
- Ready requires complete text/inventory and verified actual assets. Unknown
  inventory retains an explicit issue and unknown modality, never text-only ready.
- Covers, placeholders and empty/recommended players are not actual source media.
  A locator remains only a candidate until file/MIME/hash/audio validation succeeds.
- For asynchronously rendered Douyin video details, element existence is not
  acquisition readiness. In one bounded, cancellable readiness budget, re-evaluate
  the exact-source projection until the full caption and visible source player
  have a usable media locator. Never reload to obtain a more favorable result.
  A final strict snapshot may still be partial; a deadline cannot make it complete.
- Recheck source identity/type and challenges while waiting. A stored
  `/video/<id>` can redirect to `/note/<same-id>`; matching the numeric ID does not
  make the unsupported image-post layout a supported video. Never take its
  recommended player as the source. Exact CDN-host compatibility also requires
  an observed source player and the unchanged downloader/file/audio guards.
- Douyin caption completeness follows rendered text, not oversized inline element
  boxes. An inline `h1` can legitimately have zero client/scroll dimensions while
  its smaller descendant text is fully visible. For supported untransformed
  layouts, validate nonempty text-node Range rectangles against each clipping
  ancestor's actual clip bounds; finite positive text geometry is required.
  Do not replace this with a fixed overflow allowance or ignore hidden/unknown
  text. Unverifiable geometry, actual clipped text, visible expansion and
  ellipsis remain incomplete. Never mutate CSS to make a caption pass.
- A configured legacy line clamp is not by itself evidence that text was omitted.
  Only the verified exact-H1/direct-parent inline layout may use an additional
  bounded character/line proof: every non-whitespace Unicode character needs
  positive geometry within all clip bounds and within the allowed line slots,
  derived from the actual text's uniform positive line height. The H1's zero
  line height is not the descendant text's line height. Extra sibling/generated
  layout, shifted/mixed/unknown flow and unsupported clamping remain incomplete;
  a tall outer box alone cannot establish full text coverage.

## 4. Validation & Error Matrix

| Source condition | Required outcome |
| --- | --- |
| Exact-ID normal note, complete text, valid empty image list, proven absent video | May be text-only ready |
| Normal note with present malformed video | Unknown inventory; cannot be text-only ready |
| Usable video stream plus malformed stream entry | Candidate may remain; inventory stays unknown |
| Missing/wrong identity or ambiguous projected keys | structure_changed |
| Missing/blocked/unsupported media bytes | Explicit asset failure; never substitute its cover |
| Malformed source converted to ordinary null/empty data | Invalid implementation, even if downstream validation accepts it |
| Exact video structure exists before caption/player visibility or currentSrc | Continue bounded readiness; do not classify from the first partial snapshot |
| Caption stays collapsed/clipped or media remains missing at the deadline | Keep partial/failed acquisition; no model call or cover/text fallback |
| Video URL redirects to same-ID note layout | Fail source/type validation; not a video-readiness success |
| Inline heading has zero client dimensions but all real text fits its clip ancestors | May be complete after visibility, actual text geometry and remaining guards pass |
| Nonempty text is hidden, has unknown geometry, or crosses a clip boundary | Partial/unavailable; parent scroll dimensions cannot establish completeness |

## 5. Good / Base / Bad Cases

- Good: mixed valid/malformed streams retain usable candidates without claiming
  complete input.
- Base: a verified ordinary image note projects only allowed text/image fields.
- Bad: an invalid video array becomes null and is later treated as no video.

## 6. Tests Required

- Run real projection JavaScript in network-disabled Chromium, then the pure
  projector and materialize. Direct Python fixtures alone miss lossy JS normalization.
- Malformed video string/boolean/array/number and mixed stream entries must never
  produce ready; assert unknown inventory/modality and no unexpected private values.
- Keep positive absent/valid media cases; do not make everything incomplete just
  to satisfy negative tests. Require zero skipped browser fixtures in gated runs.
- Regression: derivative tests/test_product_media_xhs.py::
  test_javascript_preserves_unknown_inventory_for_malformed_media.
- Douyin regressions must run the real `enrich_with_context` wait/snapshot path
  against network-disabled Chromium: delay structure, caption visibility, player
  visibility and `currentSrc` separately. Also cover permanent partial captions,
  missing media, cancellation, wrong-ID and same-ID `/note/` redirects. Assert
  one navigation, no recommended-media substitution, and owned-page cleanup.
- Include a real inline large-font/zero-line-height heading with smaller child
  text: element/scroll boxes overflow but actual text ranges fit. Pair it with
  genuine horizontal/vertical clipping, hidden descendant text, unknown/empty
  range geometry, visible expansion and unsupported transforms. The positive
  fixture must fail before the text-layout fix; all negative cases stay nonready.
- Exercise legacy two-line clamp styling with both a complete two-line caption
  and genuinely omitted text beyond the limit. A configured maximum is not
  proof of omission, and computed `display: flow-root` is not proof that a
  legacy clamp is inactive. Require positive full-text geometry evidence before
  accepting such a layout; retain unknown/actually clamped cases as incomplete.
  Cover a hidden third line inside an oversized container, and zero-height
  generated text consuming a clamp line despite apparently fitting character
  rectangles. Include empty descendants with generated content. Preserve the
  observed harmless empty-content, zero-width floating pseudo-element positive
  case instead of banning all pseudo-elements indiscriminately.
  In read-only browser diagnostics, inspect vendor CSS with `getPropertyValue`
  rather than interpreting an unsupported camel-case proxy field as absence.

## 7. Wrong vs Correct

Wrong: malformed input becomes indistinguishable from absence.

```javascript
video: isPlainObject(note.video) ? projectAllowedFields(note.video) : null
```

Correct: the XHS internal projector treats an unexpected empty video object as an
unknown representation, distinct from null. Malformed stream entries retain null
sentinels so its all-object inventory test fails.

```javascript
video: isPlainObject(note.video)
  ? projectAllowedFields(note.video)
  : (note.video == null ? null : {})
```
