# Transport/model checkpoint — 2026-08-28

Status: **PASS for the four-file transport/model chunk after the scoped fix.**
This is not final summary integration or live provider acceptance.

## Scope and method

Loaded the check manifest and its referenced specifications/research, then the
current PRD, design, implementation plan, implementation boundary and API contract.
Applied `trellis-check` and refreshed `trellis-before-dev` before editing.

Reviewed only `backend/src/longtian_api/services/ai_client.py`, `ai_analysis.py`
and their two dedicated test files. Existing monitoring-rule constants and source
schemas were read to verify historical-context compatibility. Other product and
frontend owners remain active; their implementation is not signed off here.

The reviewer made local edits and narrowly synchronized only its two changed files
to the approved isolated Centaurus checkout. No user runtime/database/credentials,
browser, platform, provider call, fork edit or Git write was performed.

## Findings (fixed)

### T1 — The new context rejected valid21–100-term historical runs

File: `backend/src/longtian_api/services/ai_analysis.py`.

`AnalysisContext.terms` initially had a20-entry maximum, while the existing rule
service permits100 effective queries and collection snapshots retain those terms.
This would reject valid21–100-term run context instead of passing the entire frozen
rule to analysis/composition. The independent100-source summary limit does not
justify a20-term context limit.

Main ran the new tests against the unchanged source on Centaurus:
**2 failed,1 passed,64 deselected in0.16s**. Both21/100 positive cases failed on
Pydantic's old20-entry bound; the101-term negative case passed.

Fix: import and use the existing `MAX_TERMS_PER_RULE` owner rather than copying
another limit or truncating history. No prompt, source schema, public API or storage
contract changed. The regression verifies every term and its order in both the
analysis and final-composition prompt, with101 terms still rejected.

The existing plain/exact-fenced successful-output test was also parameterized over
`relevant`, `irrelevant` and `uncertain`, explicitly preserving a valid uncertain
judgment as success rather than technical failure. A new89-character test signature
was mechanically wrapped after Ruff identified it; the final checks are clean.

## Findings (not fixed)

No additional concrete defect was found in this frozen chunk. The following are
explicitly outside this checkpoint, not implied passes:

- Full-run admission/idempotency/configuration revision, durable item/cache reuse,
  cancellation/restart, browser lifetime, final relevant-set selection and UI/API
  consistency require the later integrated review.
- The API contract's aggregate-usage overflow exception (all token totals null and
  `complete=false`) is understood. This chunk validates individual safe-integer
  usage; the product aggregation and frontend handling have not been reviewed here.
- Multimedia admission is deliberately limited to the normalized exact Beijing
  DashScope compatible-mode base URL plus `qwen3.5-omni-plus`. Other configurations
  can receive complete text-only input, but no new multimodal compatibility, image/
  audio understanding or whole-five-platform live support is claimed.
- A strict citation validator verifies supplied IDs, not whether every generated
  factual claim is semantically supported. Attributed prompts and later authorized
  evidence/quality acceptance remain necessary; model text is not verified fact.

## Positively traced boundaries

- Analysis revalidates ready enrichment against stored source identity, complete
  coverage/inventory, asset count and fingerprint. Every in-memory media blob must
  match its asset ID, MIME, exact byte size and SHA256. Missing/extra/changed assets
  fail before a model request; snippets, covers and source URLs are not substitutes.
- Actual JPEG/PNG/WebP images and the audio-bearing MP4 bytes are inline once each.
  The video uses the reviewed `data:;base64,` form; there is no separate audio request,
  frame extraction, conversion, remote file upload or transport fallback.
- Existing6MiB aggregate,24-image/one-video and20,000-character content bounds remain.
  The serializer checks the exact UTF-8 JSON bytes that the HTTP client sends against
  the strict `<9,000,000` boundary before DNS. Tests cover the exact byte boundary
  and multibyte text, not just Python string length.
- The existing DNS/IP pin, original TLS SNI/Host, no proxy/redirect/retry and bounded
  network phases remain. Analysis/composition expose180-second and2048/4096-token
  constants; the client rejects a deadline above180 seconds. Caller integration is
  for the next checkpoint. The connection test remains its original tiny text-only
  32-token/30-second contract without a usage-option API change.
- SSE requires valid final text, stop and DONE within its byte limits. Only final
  content and validated recognized numeric usage survive; private metadata/reasoning
  are discarded. Missing, malformed or conflicting accounting stays unknown, not
  zero; duplicate identical usage is deterministic and sparse modality details are
  not invented. Valid usage cannot turn a partial/refused stream into success.
- Only exact whole-response JSON fences are removed. Duplicate keys, prose/trailing
  data, invalid enums/types/extra fields, empty or unknown citations fail without a
  repair call. Local JSON/schema/credential failures carry the already validated
  usage with bounded stage/code, not a retained raw-answer field.
- Literal and bounded escaped credential sentinels are checked before accepting
  model prose. Prose is non-executable data; the model cannot choose links, tools,
  files, browser navigation or a new destination.
- Composition builds messages from typed application-supplied source records/IDs,
  saved full text and bounded analysis plus reconciled application counts. They are text
  only; empty evidence or a prompt over120,000 characters fails before composition,
  without truncation, splitting or media re-upload.

## Verification

Main's original frozen focused checkpoint was151 passed in0.48s. The red regression
above was main-run. After the local fix, the reviewer executed the following only
in `/tmp/longtian-media-validation.DeYMEC/backend` on Centaurus:

```sh
PYTHONPATH=src .venv/bin/pytest -q tests/test_ai_client.py tests/test_ai_analysis.py --tb=short
.venv/bin/ruff check src/longtian_api/services/ai_client.py src/longtian_api/services/ai_analysis.py tests/test_ai_client.py tests/test_ai_analysis.py
.venv/bin/ruff format --check src/longtian_api/services/ai_client.py src/longtian_api/services/ai_analysis.py tests/test_ai_client.py tests/test_ai_analysis.py
```

- Final tests: **160 passed in0.46s**, zero skips and no reported warnings.
- Ruff: **pass**. Format: **4 files already formatted**.
- TypeCheck: no separate Python type-checker is configured/reported for this gate;
  no independent type-check pass is claimed.
- Tracked scoped `git diff --check`: pass. This is not a whole-worktree review.
- Local and isolated remote SHA256 matched for all four reviewed files:

| File | SHA256 |
| --- | --- |
| services/ai_client.py | `3d67011f12db83f86893cc132e5e9f330280c767681378d0a4809609610f90a7` |
| services/ai_analysis.py | `fb3a93c9b73debf59e8bc1f2b59fcf72c994841d0d37a0acfadf391bea27ebbf` |
| tests/test_ai_client.py | `c62cd90baad0dab89c6024c57362ad214b0dfb98de3329dd4c59fb914e2acd47` |
| tests/test_ai_analysis.py | `d164b83c1a91954204117a9f2def64708e69a810bc32dfd2b4fd4ffb313b84fd` |

Reviewer writes are only `ai_analysis.py`, `test_ai_analysis.py` and this report.
No spec change is required to authorize the fix: it restores the already approved
whole historical-context contract. Source is frozen for the next integration gate.
