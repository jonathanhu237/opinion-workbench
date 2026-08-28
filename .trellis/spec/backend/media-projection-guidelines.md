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

## 4. Validation & Error Matrix

| Source condition | Required outcome |
| --- | --- |
| Exact-ID normal note, complete text, valid empty image list, proven absent video | May be text-only ready |
| Normal note with present malformed video | Unknown inventory; cannot be text-only ready |
| Usable video stream plus malformed stream entry | Candidate may remain; inventory stays unknown |
| Missing/wrong identity or ambiguous projected keys | structure_changed |
| Missing/blocked/unsupported media bytes | Explicit asset failure; never substitute its cover |
| Malformed source converted to ordinary null/empty data | Invalid implementation, even if downstream validation accepts it |

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
