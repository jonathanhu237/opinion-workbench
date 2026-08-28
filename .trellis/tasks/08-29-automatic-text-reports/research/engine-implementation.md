# C pure text engine implementation

Status: engine sources released to backend core for integration; focused engine
checks passed on the isolated Centaurus snapshot. This is not the complete C
quality gate or live-provider acceptance. Parent/main owns the final gate.

## Scope and ownership

Implemented only:

- `backend/src/longtian_api/schemas/topic_report_engine.py`: strict internal
  source/context, judgment, leaf/overview, call, result/reuse and planning models.
- `backend/src/longtian_api/services/topic_report_engine.py`: synchronous pure
  request planning, exact-size preflight, strict output/citation validation and
  compatibility hashes.
- `backend/tests/test_topic_report_engine.py`: synthetic, engine-only fixtures
  and 175 focused parameterized tests.
- This evidence file. Main additionally approved documenting the small
  `output_digest` seam addition in `research/text-engine-contract.md`.

No core repository, migration, API, lifecycle, shared helper, frontend or Git
mutation. No new dependencies. Existing A/B changes remain intact. The
before-development guidance kept the engine at this narrow boundary; quality
review verified the shared helpers and recorded exact remote checks.

## Exported integration seam

Schemas follow the accepted engine contract, including `NodeKind`, `NodeKey`,
`Sha256`, `ProviderIntent`, `TextPrompt`, `EngineContext`, `FrozenTextSource`,
`Judgment`, `RelevantSource`, leaf/overview paragraph and document models,
`ChildOverview`, `PreparedCall`, `ValidatedOutput`, `CompletedOutput`,
`RequestProof`, `LeafPlan`, `OverviewCallPlan`, `OverviewCarryPlan`, and the
discriminated `OverviewPlan` union.

The service exports:

```python
ENGINE_VERSION = "topic-text-engine-v1"
prepare_judgment(context, source) -> PreparedCall
take_leaf(context, candidates, *, position) -> LeafPlan
take_overview(context, children, *, level, position) -> OverviewPlan
check_request(call, configuration) -> RequestProof
parse_completion(call, completion, *, api_key) -> ValidatedOutput
validate_reuse(call, saved, *, api_key) -> ValidatedOutput | None
canonical_hash(value) -> Sha256
output_digest(kind, output) -> Sha256
```

`output_digest` is the only addition to the pre-dispatch seam, explicitly
approved by main at core's request. It accepts an already decoded object or
typed output, strictly revalidates the corresponding kind and nested values,
then hashes exactly:

```json
{"kind":"<judgment|leaf|overview>","schema_version":"topic-report-v1","output":"<actual validated object, not this placeholder string>"}
```

The manifest is serialized with compact sorted-key JSON, `ensure_ascii=False`,
`allow_nan=False`, then strict UTF-8 SHA-256. No fallback to `str(value)` or
non-string object keys. The digest alone does not establish graph membership,
source coverage or credential safety.

## Evidence and request behavior

- Reconstruct nested models at each preparation/validation boundary; an outer
  frozen model does not authorize later mutations of its lists. Saved-ready
  checks cover full text bounds, inventory and modality consistency, extractor
  identity, complete asset metadata and original A prompt/hash/schema. They do
  not acquire bytes or reconstruct the upstream media fingerprint.
- Preserve exact accepted text and custom instructions; reject invalid UTF-8,
  NUL, blank generated prose and whitespace-only business prompts. UTC timestamps
  normalize before evidence hashing. No source title/snippet fallback replaces
  saved full text.
- Judgment sends original result ID/platform/publication text, saved full text,
  all Understanding fields and bounded coverage metadata. Original URLs, media
  bytes/blob handles, author profiles and provider settings are absent from the
  model's source projection. Business instructions remain separate from
  app-owned evidence/output/privacy instructions.
- Leaf input is a strictly increasing, unique 1–8 source buffer containing only
  relevant judgments. The largest fitting prefix is returned with its consumed
  count; core keeps the suffix and fills subsequent buffers across DB pages.
- Overview input is 1–8 distinct completed child projections. Calls consume at
  least two and at most eight; a final single child is returned unchanged as
  `carry`. A non-fitting pair fails rather than creating a nonreducing call.
  Only child keys and bounded overviews enter its user message, never a growing
  descendant-ID array. Core must use carry only at true end-of-input.
- Every request includes the exact app instructions, custom instructions and
  serialized user envelope in the inclusive 120,000-character check. Escapes
  count as sent characters, not raw source lengths or UTF-8 byte estimates.
  A single oversized source fails with `request_too_large`, without clipping.
- Import shared budgets: 2,048 tokens for judgment; 4,096 for leaf/overview;
  180 seconds; existing encoder enforces strictly fewer than 9,000,000 bytes.
  `check_request` passes exactly two text messages and `include_usage=True` to
  the existing encoder, returning the exact byte length and wire SHA-256.
- Leaf citations must be unique within each paragraph and their union must
  equal all admitted source IDs. An overview may cite a subset of supplied
  children, but never an unknown child. No output field can supply source URLs
  or authoritative descendant membership.
- Parsing reuses `answer_object` and checks each decoded prose string with the
  existing `check_credential`. Strict JSON/fence, duplicate key, NaN, schema,
  wrong union, repeated/unknown/omitted citation and credential failures remain
  bounded constant `AIAnalysisError`s. Validated completion usage survives local
  parsing/citation/credential failures; invalid usage remains unknown.
- Reuse requires matching engine version and fresh input hash. Matching outputs
  are revalidated for kind, shape, citations, digest and current credential.
  Corrupt matching rows fail closed. Historical usage is not charged or carried
  by the engine.

## Important trust boundary agreed with core/main

`PreparedCall` does not carry the complete provider/context/dependency manifest
behind `input_hash`. It is an audit projection, not executable authority.

Core **always regenerates** it from the frozen evidence and validated current
graph before preflight/reuse. Core compares that fresh hash with persisted rows
and verifies the lease equals the frozen provider intent before marking a call
attempted. Engine rechecks call kind, logical key, actual message lengths,
membership (including strict integer rather than `True == 1`), output budget and
exact wire encoding. It cannot reconstruct hidden dependency/provider proof
from a persisted call alone and does not claim to do so.

Source-evidence hashes bind the entire revalidated `FrozenTextSource`, including
its full input, upstream fingerprint and immutable initial prompt/provider.
Request hashes bind context, kind/key, exact messages, ordered evidence or child
dependency hashes and budgets. Changing a child's details/membership changes
compatibility even when its overview text does not. Logical keys are canonical
JS-safe decimal `judgment:<result_id>`, `leaf:<position>` and
`overview:<positive-level>:<position>`; retry database IDs do not enter them.

Core retains provider calls/leases, graph and source membership proof, attempts,
transactional settlement, usage aggregation, retry, cancellation and lifecycle.
The engine does not call a model, browser, media worker, filesystem or database,
spawn tasks, sleep, retry, acquire a lease, or read the current clock.

## Focused remote validation

Backend core granted a serialized source window and initially synced exactly
the three owned engine Python files into:
`Centaurus:/tmp/longtian-decoupling-impl.dMCxsd/backend`.
All subsequent changes were local `apply_patch` edits; only the explicit owned
service file was re-synced. No whole-package sync, deletion or remote source edit.

Final commands and results:

```text
uv run --frozen ruff check src/longtian_api/schemas/topic_report_engine.py \
  src/longtian_api/services/topic_report_engine.py tests/test_topic_report_engine.py
All checks passed!

uv run --frozen ruff format --check src/longtian_api/schemas/topic_report_engine.py \
  src/longtian_api/services/topic_report_engine.py tests/test_topic_report_engine.py
3 files already formatted

uv run --frozen python -m pytest -q tests/test_topic_report_engine.py --tb=short
175 passed in 0.87s
```

The first test run found six escaped-credential cases after 169 passes. The
cause was applying the helper to reserialized JSON instead of each decoded
prose field. The engine-local correction rejects those cases with preserved
usage; no shared credential helper changed. An earlier Ruff line-length issue
was also fixed before the final checks.

Coverage includes all three output shapes; Unicode/escaped exact 120,000 and
over-limit/custom-prompt checks; 1/8/9/101/1001 source partition coverage;
multilevel overview reduction/final carry; citations; nested input/output
mutations; source/dependency/prompt/provider hash changes; strict canonical
JSON; exact wire encoding; retry compatibility; and forbidden I/O entry points.
The no-I/O test guards file opening, socket creation, SQLite connections and
model completion while invoking every public engine operation.

Final local `shasum -a 256` and remote `sha256sum` matched:

| File | SHA-256 |
| --- | --- |
| `schemas/topic_report_engine.py` | `9fdb6fd7c31db41f4344e6a006fff197ecc66f966fe432c3aa00be6f8ab12e92` |
| `services/topic_report_engine.py` | `f462c5b7beb33886338c0a6586886de31a36dc5932e7ecaba009332b0a88eb2f` |
| `tests/test_topic_report_engine.py` | `0dcae0390ea1dc6c9fd148f959f256809364116a0959571e2b1aed339db5a4e0` |

Three explicit-file `rsync -aicn` checks subsequently returned exit 0 with no
changes. The remote window and engine sources are released to backend core.

## Remaining integration gates and risks

- Core must run the merged full backend suite and verify fresh reconstruction,
  lease/context mismatch, durable graph/call boundaries, accounting and retries.
- Main owns complete C/parent integration and frontend/browser acceptance.
- No live model/media/account operation, real schedule activation, production
  database, deployment or commit was performed. Synthetic contracts do not prove
  model relevance quality or real geographic accuracy. Character limits are
  not a promise about a provider's token context capacity.
