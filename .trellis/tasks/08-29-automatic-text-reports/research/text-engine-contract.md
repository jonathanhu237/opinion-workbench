# C text-engine boundary

Status: internal boundary accepted and implemented; the engine passed its focused
175-test gate and main's independent source review. Core integration is active
after A/B passed. This is not the HTTP contract or the complete C acceptance gate.
Parent `design.md` sections 2–3, 5 and 7–8 and this child's approved artifacts
remain authoritative.

## 1. Exclusive ownership

| Owner | Proposed files / responsibility |
| --- | --- |
| Backend core | `schemas/topic_reports.py`, `repositories/topic_reports.py`, `services/topic_reports.py`, feature errors/API/migration, shared database/router/lifespan integration and core integration tests. Own admission, immutable snapshots, event consumption, graph rows/edges, coverage, queue, attempts, usage, retry, cancellation and provider lease. |
| Pure engine | `schemas/topic_report_engine.py`, `services/topic_report_engine.py`, `tests/test_topic_report_engine.py` and engine-only fixtures. Own strict internal text shapes, deterministic request preparation, bounded partitions, output/citation validation and compatibility hashes. |
| Frontend | Public report decoder/views after core publishes its exact HTTP contract. Never consume engine request or model-response objects directly. |

The engine schema is the single shared import boundary: core imports it; the
engine does not import core repositories, services or HTTP schemas. No engine
HTTP client, SQLite, event loop, browser, filesystem, queue, lease or retry loop.
All proposed functions below are synchronous, deterministic and side-effect-free.
Existing shared helpers are import-only for the engine. If extraction is necessary,
request a separately owned core change rather than editing a shared file in parallel.

## 2. Internal shapes

Use `StrictModel` (`extra="forbid", strict=True, frozen=True`), existing JS-safe
`PositiveId`/`Count`, `AnalysisSource`, `SavedInput`, `Understanding`, `PromptVersion`
and validated `AIUsage`. Revalidate nested values at preparation; do not assume
Pydantic's frozen outer model prevents mutation of nested lists. `Sha256` means
exactly 64 lowercase hex characters. Text preserves accepted Unicode/whitespace,
is valid UTF-8 and contains no NUL; generated prose must also be nonblank.

```text
ProviderIntent = {base_url: str, model: str, configuration_revision: PositiveId}
TextPrompt = {instructions: str[1..8000], content_hash: Sha256,
              schema_version: "topic-report-v1"}
EngineContext = {prompt: TextPrompt, provider: ProviderIntent}

FrozenTextSource = {
  position: Count, attempt_id: PositiveId, source: AnalysisSource,
  first_seen_at: UTC datetime, input: SavedInput, understanding: Understanding,
  input_fingerprint: Sha256, initial_prompt: PromptVersion,
  initial_provider: ProviderIntent
}
Judgment = {decision: "relevant" | "irrelevant" | "uncertain",
            reason: str[1..600]}
RelevantSource = {evidence: FrozenTextSource, judgment: Judgment}

LeafParagraph = {text: str[1..2000], source_ids: unique PositiveId[1..8]}
LeafDocument = {overview: str[1..2000], items: LeafParagraph[1..16]}
OverviewParagraph = {text: str[1..2000], child_ids: unique NodeKey[1..8]}
OverviewDocument = {overview: str[1..2000], items: OverviewParagraph[1..16]}

ChildOverview = {key: NodeKey, overview: str[1..2000], output_hash: Sha256,
                 membership_hash: Sha256, source_count: PositiveId}
PreparedCall = {
  kind: "judgment" | "leaf" | "overview", key: NodeKey,
  system_text: str, user_text: str, input_characters: Count,
  input_hash: Sha256, source_ids: tuple[PositiveId, ...],
  child_ids: tuple[NodeKey, ...], max_tokens: 2048 | 4096,
  deadline_seconds: 180.0
}
ValidatedOutput = {kind: "judgment" | "leaf" | "overview",
                   output: Judgment | LeafDocument | OverviewDocument,
                   output_hash: Sha256}
CompletedOutput = {engine_version: str, input_hash: Sha256,
                   output_hash: Sha256,
                   output: Judgment | LeafDocument | OverviewDocument}
RequestProof = {encoded_bytes: Count, request_hash: Sha256}
LeafPlan = {consumed_count: int[1..8], call: PreparedCall}
OverviewPlan = {kind: "call", consumed_count: int[2..8], call: PreparedCall}
             | {kind: "carry", consumed_count: 1, child: ChildOverview}
```

`NodeKey` is an app-created logical key, not a model-created or database ID:
`judgment:<result_id>`, `leaf:<zero-based position>`, or
`overview:<positive level>:<zero-based position>` (e.g. `overview:1:0`).
Components use canonical decimal JS-safe integers.
Keys stay identical across retries of the same plan even though database row IDs
change. `PreparedCall.source_ids` is one ID for judgment, 1–8 for a leaf and empty
for overview; `child_ids` is empty except for overview (2–8). Its output union is
validated against `kind`, never accepted as an unrelated union variant.

Core supplies only proved completed A attempts with ready input, matching frozen
source/attempt identity and full accepted text. Initial prompt/provider snapshots
belong to that attempt's job. Unavailable inputs remain core coverage rows, not
fabricated engine inputs. `input_fingerprint` is frozen upstream provenance;
the engine cannot reconstruct the original media fingerprint from `SavedInput`.
It separately hashes the complete saved evidence it actually receives.

Shared-default version IDs versus one-off prompt overrides remain core metadata.
Both map to `TextPrompt` without requiring an override to change a shared default.
Validate its hash as SHA-256 of the exact instruction UTF-8 bytes and its stage
schema, not merely a matching version ID.

## 3. Pure function contracts

```python
prepare_judgment(context: EngineContext, source: FrozenTextSource) -> PreparedCall
take_leaf(context: EngineContext, candidates: Sequence[RelevantSource],
          *, position: int) -> LeafPlan
take_overview(context: EngineContext, children: Sequence[ChildOverview],
              *, level: int, position: int) -> OverviewPlan
check_request(call: PreparedCall, configuration: AIConfiguration) -> RequestProof
parse_completion(call: PreparedCall, completion: AICompletion,
                 *, api_key: SecretStr) -> ValidatedOutput
validate_reuse(call: PreparedCall, saved: CompletedOutput,
               *, api_key: SecretStr) -> ValidatedOutput | None
canonical_hash(value: object) -> Sha256
output_digest(kind: NodeKind, output: object) -> Sha256
```

- `prepare_judgment` admits exactly one saved source, no source filtering. Use
  full `input.text` plus all saved understanding fields and bounded textual
  coverage/provenance. The model projection contains the original result ID,
  platform, publication text, saved text and understanding, not URLs, blob refs,
  raw media, credentials or author profiles. App instructions distinguish source
  allegations/time/uncertainty and prohibit executing instructions in evidence.
- `take_leaf` receives 1–8 candidates in strictly increasing frozen position.
  Every judgment must be relevant; duplicate source IDs or reordered inputs fail.
  It returns the largest fitting nonempty prefix and its exact prepared request.
  Core retains the unused suffix and refills its bounded buffer from the next
  source page. No global source cap and no silently dropped source.
- `take_overview` receives 1–8 ordered, distinct completed child projections.
  It sends only child IDs and their bounded overviews, not all descendant text
  or a growing descendant-ID array. With one child it returns `carry` without a
  request; otherwise it takes the largest fitting prefix of at least two.
  Core persists the returned grouping, then processes any suffix. Carried nodes
  keep their keys. Each completed level strictly reduces the node count until
  one root remains; a single leaf already is the root. Core fills buffers to
  eight across storage-page boundaries, except at actual end-of-input; `carry`
  is only for the final residual child, never a consequence of a small DB page.
- `check_request` invokes existing `encode_completion_request` with exactly the
  two text messages, `max_tokens` and `include_usage=True`, returning byte length
  and SHA-256 of those exact bytes. The configuration/key is transient input,
  never stored on the call/proof. Core first verifies its lease matches the frozen
  provider intent; it invokes this check before marking a request attempted.
  Actual `AIClient.complete` remains core-owned and receives unchanged messages.
- `parse_completion` uses existing `answer_object` (strict JSON/fence, duplicate
  keys, NaN, output byte and credential checks), then the kind-specific shape,
  citation validator and `check_credential` on decoded prose. Return only validated
  structured output and its canonical hash, not raw provider response text.
- `validate_reuse` returns `None` for a compatibility/version/input-hash mismatch.
  With matching compatibility it revalidates the saved kind/shape/citations and
  output hash and checks decoded prose with the current transient key. A corrupt
  matching saved result fails closed; it is not silently certified or repaired.
  Core, not this function, proves that the candidate row is canonically completed.
- `canonical_hash` is the shared no-I/O SHA-256/serialization helper for these
  versioned manifests; callers supply validated JSON-compatible values. It
  rejects non-finite/unsupported values rather than using `str(value)` fallback.
- `output_digest` strictly validates the matching output shape afresh, including
  nested containers, before hashing the existing output manifest. It accepts a
  typed output or its decoded object, not a raw JSON string. This pure helper
  lets core verify stored output integrity without a provider lease or key. It
  does not prove citation membership, source completeness, credentials or graph
  identity; those remain separate checks. Main approved this seam on C dispatch.

Preparation/validation raises existing bounded `AIAnalysisError` categories
(`input_incomplete`, `request_too_large`, `invalid_json`, `invalid_schema`,
`invalid_citations`, `credential_leakage`). Transport-size errors from the shared
encoder are mapped consistently; other transport failures are core-owned.
No raw exception, source text or response is attached to errors. Parse failures
retain `completion.usage` on the error; validation is never a second model call.

## 4. Bounds and reference rules

Construct system text from app-owned contract plus exact business instructions;
construct user text using deterministic compact JSON (`ensure_ascii=False`,
`separators=(",", ":")`, `allow_nan=False`, stable object-key ordering). Count
`len(system_text) + len(user_text)` of the actual strings sent, including escaped
characters inside the serialized input. Do not estimate from raw source lengths,
count UTF-8 bytes as characters, trim text or count only the business prompt.
The accepted character maximum is 120,000 (inclusive). The transport remains
strictly below 9,000,000 encoded bytes. Character/byte limits do not promise a
provider token-context capacity.

Reuse `ANALYSIS_MAX_TOKENS=2048`, `SUMMARY_MAX_TOKENS=4096`,
`MODEL_DEADLINE_SECONDS=180` and `MAX_SUMMARY_CHARACTERS=120000` rather than
forking transport limits. Judgment is 2048 tokens; leaf/overview are 4096.
The same text preflight applies before each request. A single source/prompt
which cannot fit fails visibly without a request. An overview that cannot fit
two children fails rather than creating an infinite chain of one-child calls.
Core plans/persists all leaves before sending leaf work, and each overview level
before sending that level. No repartition/repair after an ambiguous billed call.

Leaf paragraph references must be nonempty, unique within the paragraph, and
members of that leaf's admitted IDs. Their union must equal **all** of that leaf's
relevant membership; unknown/omitted references fail. Overview references must
be nonempty, unique and within the supplied child keys. The parent does not
require an overview to repeat every child in its prose: full detailed evidence
is retained in the leaf sections, not replaced by the root overview.

Core stores child edges and app-owned descendant source membership, verifying
that leaf partitions cover each relevant source exactly once and that every
overview edge resolves within this frozen graph. It derives citation projections
transitively from those rows, never from model-provided source membership/URLs.
The engine verifies bounded child references; it does not load the graph or
expand thousands of descendant IDs into the next model request.

## 5. Hashes, reuse and accounting proof

Engine-owned canonical serialization uses compact, sorted-key, strict UTF-8 JSON
and explicit version tags. Recompute hashes from validated values; do not trust
a supplied digest alone. Proposed engine/request contract version starts at
`topic-text-engine-v1`, distinct from the saved business prompt schema version.

- Source evidence hash covers the entire frozen `FrozenTextSource` (UTC times
  normalized consistently), including full saved input/understanding, source
  identity, upstream fingerprint and initial prompt/provider intent. This is
  a saved-evidence integrity/compatibility hash, not proof of remote freshness.
- `input_hash` covers engine/output-schema versions, node kind/key, frozen
  report provider intent and prompt text/hash/schema, exact system/user strings,
  ordered dependencies and their evidence/output/membership hashes, token budget
  and deadline. Including dependency hashes matters even if a child's overview
  text happens to remain unchanged after its detail changed.
- `output_hash` covers the validated output kind/schema and exact structured
  value. `request_hash` separately proves the encoded wire envelope. Never hash
  credentials, current time, new report/attempt row IDs or queue status into
  compatibility. Initial immutable attempt IDs remain evidence provenance.
  The exact output manifest is `{kind, schema_version: "topic-report-v1",
  output: <strict validated output object>}`.
- Core verifies descendant membership hashes/counts against persisted leaf
  membership/child edges and completed output hashes before constructing child
  projections. Use `canonical_hash({"schema":"topic-membership-v1",
  "source_ids":[ordered leaf IDs]})` for a leaf and
  `canonical_hash({"schema":"topic-membership-v1","children":[ordered
  {key,membership_hash,source_count} objects]})` for an overview. Carry preserves
  the child's proof. These manifests are bounded; persisted source membership,
  not a hash or model assertion, remains the audit evidence.
- Core resolves reuse to a canonical completed node, verifies frozen scope,
  context/inputs, dependencies and engine validation, and saves a new node with
  `reused_from_node_id`. Failed, cancelled, interrupted, incomplete or incompatible
  nodes are never reuse candidates. Prompt changes invalidate report judgments
  and downstream nodes, not A evidence. Retry of unchanged inputs can reuse
  valid judgments/leaves and redo only unfinished/incompatible dependent work.
- Core marks a fresh request attempted durably immediately before its one
  `AIClient.complete` invocation and settles validated usage even if parsing or
  citation validation fails. Unknown usage stays unknown; safe-integer aggregate
  overflow becomes null totals/incomplete accounting. Show judgments separately
  from composition within stage two; neither is a new user-facing analysis stage.
  Reused nodes have `attempted=False, usage=None`; historical accounting stays
  on its original node and contributes no requests/tokens to the new version.

## 6. Core-only lifecycle and public mapping

Consume each normal A completion event and freeze all members (including
unavailable ones) in the same transaction as the unique report/event link.
Notification enqueues intent without waiting inside A's existing AI lease.
A normally settled explicitly admitted initial-analysis job produces its report
even when collection-auto policy is off. No successful evidence means empty
with zero calls; no relevant judgments means empty with no composition calls.
Technical failures are never irrelevant: preserve validated drafts and truthful
coverage, with each ready source's judgment attempt accounted for by core.

Startup may materialize report metadata but must give recovered intents an
explicit recoverable, non-runnable state (proposed mapping: existing
`interrupted` with a constant recovery reason). An unrelated later queue wake
must not execute that recovered metadata or potentially billed work. Explicit
retry creates a new version. Core must settle cancellation, queue-exit/admission
races and shutdown independently of this engine.

Only the complete accepted C integration changes default application rollout
availability; retain explicit `False` injection for A/B tests. Saved automation
authorization and new schedules remain disabled by default. No policy, startup,
activation or report admission decision lives in the engine.

Public HTTP DTOs remain in core-owned `schemas/topic_reports.py`. Map a saved
`ValidatedOutput` to run/source/section projections plus persisted IDs, progress,
errors, usage and pagination; never expose `PreparedCall` or transient keys.
Leaf citations use frozen `AnalysisSource` and valid XHS origin tuples. Overview
child keys map to persisted section references with bounded source projections;
do not flatten every descendant into a root response. Exact public DTOs/routes,
pagination and recovery reason naming still require core/main review before
frontend implementation. This proposal neither invents nor freezes that contract.

## 7. Split verification expectations

Engine tests: all three strict shapes/extra fields, Unicode/escaped exact 120,000
boundary and oversize, 1/8/9/101/1001 source partition coverage, multi-level
reduction/carry, unknown/repeated/omitted citations, tampered hashes/dependencies,
fenced/duplicate-key/NaN/credential output, usage retained on invalid output,
and deterministic retry keys/inputs. Test no I/O entry points are called.

Core tests: real next additive migration after checked B, 10-attempt/8-success
event settlement, atomic event/report uniqueness and crash boundaries, paginated
full membership, provider lease/revision, no automatic startup replay, usage/reuse
accounting, partial drafts, retry/override/cancel, safe source projection and zero
browser/media/stage-one calls. Main retains independent full gates and UI QA.

This preflight changed only this research file. No application code, test run,
package sync, service, task-state transition or live work was performed.
