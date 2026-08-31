# Independent Media Cost Probe Check — 2026-08-28

## Initial pre-live verdict and scope

The frozen task-local harness has no remaining pre-live blocker for the approved
single execution of at most three existing MP4 samples. Main must first stop the
idle production backend: the reused service lease is process-local, not a lock
against another application process. This review authorizes no extra sample,
retry, media conversion, model change or production feature.

The reviewer read the task manifest, PRD/design/implementation addenda, probe plan,
applicable specifications, existing AI settings/client source, the local transport
research and sanitized acquisition record. Only this report was written. The
reviewer did not access runtime data, originals, credentials, browsers or providers,
run tests, or change product/submodule source.

Reviewed frozen SHA-256 values:

```text
77bc6b194f5ad9075e75b93ed74823582a4ea18cea6a1aa55b0946289363a886  verification/media_cost_probe.py
8c06d7e673e831a1084d9f558c4e2ff1654117bd5c8a1577526f64d4d7520dc3  verification/test_media_cost_probe.py
```

## Findings (fixed)

- The initial request ceiling used 9 MiB and allowed equality. Main and the reviewer
  identified the mismatch; the implementer changed both pre/post-wrapper checks to
  reject `>= 9_000_000` bytes. The frozen tests cover equality and overflow before
  dispatch. No reviewer product-source fix was made.

## Findings (not fixed)

No unresolved implementation blocker within this disposable experiment's scope.
The following are explicit operational or evidence limits, not implemented product
capabilities:

- Actual codec, audio-track presence, duration and original-file completeness are
  main's prior `ffprobe`/source checks. The harness independently checks private
  file safety, bounded bytes, MP4 header and strict manifest values; it is not a
  full media decoder. No frame-only substitution or separate audio request occurs.
- The reviewed provider research documents one inline `video_url` MP4 carrying
  sound. An AAC track alone does not prove model hearing. Positive audio usage
  establishes reported audio processing, not accurate understanding of every word.
- These three selected samples are qualitative, not a precision/recall benchmark.
  Actual results and costs remain pending; no paid request was replayed by this
  reviewer. Missing usage/details must remain unknown, not zero or guessed billing.

## Verified paths

- One to three unique source IDs/media paths; raw media at most 6 MiB each, stated
  duration at most 90 seconds, and complete outgoing JSON strictly below 9,000,000
  bytes. The transport rejects a fourth dispatch, counts attempted requests before
  sending, and the sample loop stops after the first failure. There is no repair,
  alternate provider, conversion, final-summary or automatic retry call.
- Existing `AISettingsService.operation(1)` owns the stable credential lease.
  Expected revision, model and HTTPS base URL must match before upload. SQLite is
  opened `mode=ro` with `query_only`; initialization raises, and no save/write path
  is called. The lease exits on success, failure and cancellation.
- Each request uses the existing `AIClient.complete_text`, a 180-second deadline,
  `max_tokens=1200`, streaming and text-only output. The task transport adds only
  `stream_options.include_usage=true` and preserves the pinned destination, TLS
  SNI, Host, timeouts and credential header. TLS verification remains enabled;
  environment proxies, redirects, retries and keep-alive reuse remain disabled.
- The original MP4 is inline `data:;base64,` under `video_url`; no signed media URL,
  local media path, cookie or browser credential is added to the prompt. Scope,
  source publication text and the experiment reference date are explicit. Source
  instructions and model output remain untrusted, with no tools or actions.
- The response tee retains only whitelisted nonnegative integer usage, consistency
  checked totals and a model-name equality flag. The same bytes still pass through
  the product's bounded UTF-8/SSE, successful-stop and DONE checks. Hidden reasoning,
  unknown usage fields, error bodies and raw exceptions are not saved as evidence.
- Output is exclusively created with no-follow semantics and mode 0600 before
  client construction or credential access. Existing files are preserved. Private
  input reads reject unsafe ownership, permissions, symlinks and hardlinks. A
  bounded progress report is flushed around calls; stdout contains only fixed
  status/count projections. Only strict bounded analysis data, not raw streams,
  enters the private report. Main owns its later sanitization and cleanup.

## Verification

- **Independent static review:** completed, including frozen hashes and all fake
  tests. No test or provider execution by the reviewer.
- **Lint/format:** scoped checks passed, reported by the implementer.
- **Tests:** main ran the exact two-file snapshot on Centaurus: **28 passed in
  0.17 seconds** using fake transports and synthetic credentials only. Main also
  confirmed local/remote AI client and AI settings source hashes match.
- **Input validation:** main's local `--validate-only` accepted all three samples;
  that branch constructs no database/service/client and makes no provider call.
- **Type check:** no separate gate run or claimed; production source is unchanged.
- **Live quality/cost at this initial gate:** pending sanitized actual results; this pre-live check is
  not a claim of successful audio/video understanding or integrated AI acceptance.

## First actual invocation and bounded diagnostic correction

Main reports that only content 370 was sent, once, in the first invocation. The
completed AI-client text stream reached local answer processing, which failed
with `probe_invalid_response` after 7.091 seconds. The old harness discarded that
answer; its exact JSON/schema mismatch and substantive judgment remain unknown.
This is a failed analysis sample, not a successful classification or evidence that
a particular Markdown fence caused the failure.

The retained numeric usage is internally consistent: 22,230 input tokens = 597
text + 21,386 video + 247 audio; 292 text output; 22,522 total. Given main's checked
Beijing list prices (7 CNY/million non-audio input, 53 audio input, 40 text output),
the arithmetic is `(22230 - 247) * 7 / 1e6 + 247 * 53 / 1e6 + 292 * 40 / 1e6 =
0.178652 CNY`. This is a list-price estimate, not observed billing or proof of
accurate audio/video understanding. The reviewer performed no provider access.

Main restored the production backend while the task-local correction was prepared.
The only remaining authorized inputs are original IDs 63 and 372, once each; 370
must not be retried. The experiment's cross-invocation budget is therefore **1 + 2
= at most 3**. This depends on main's verified remaining manifest, not a claim that
the per-process transport counter is a durable cross-process quota.

The reviewer read the narrow correction and its ten additional fake cases, and
independently matched these frozen SHA-256 values:

```text
1ac9a0f8f9a8b1a43e05d4a2d176a4e25f80d96802fbb2d7b0715aa3284f1543  verification/media_cost_probe.py
5f251b60c2b5012b2c8103902d83b103c24a4c1a4733ff145905bfa01936d083  verification/test_media_cost_probe.py
```

No additional static blocker was found:

- A complete final answer first passes the literal credential check. If JSON
  decoding succeeds, a second check inspects decoded values before schema use.
- Only local JSON-decode or strict-schema failures retain at most 2,048 characters
  of that final answer as plain private JSON data, with an explicit truncation flag
  and failure stage. This captures no SSE frames, hidden reasoning or provider
  error body, and never prints answer text on stdout. Successful answers retain
  the existing strict structured projection.
- Only one exact whole-answer `json` fence is optionally removed. Extra surrounding
  prose is not repaired, and schema requirements are unchanged.
- Only those two local output failures may advance to the next unique input.
  Provider, stream, credential-safety and unexpected failures still stop; no sample
  is retried and no repair/composition request is made. Mixed local failures remain
  explicit `completed_with_output_errors`, never all-success.
- The existing lease, read-only database, private output, network, token, byte and
  call bounds are unchanged. Main must again stop the production backend before
  the remaining invocation.

Main subsequently reported **38 fake tests passed in 0.26 seconds** on Centaurus.
A cwd-dependent import-order finding was corrected only by placing Pydantic
imports above the blank line separating application imports. Main resynchronized
and reran all 38 tests, Ruff and format successfully. The reviewer checked the
new import layout and final hashes; no semantic source change was reported:

```text
d0db002264dbbc071d4a89bcda6417b1ae273361c411e3344a3afc631ce5f358  verification/media_cost_probe.py
adae7d1a25a93d99653c4a4695474a0c67781e164e8ff237cddcbf29a1f470fd  verification/test_media_cost_probe.py
```

Main's `--validate-only` accepted exactly two remaining entries, IDs 63 and 372.
The pre-invocation conditions therefore passed for those two originals once each,
after another confirmed production-backend stop. No further paid result or quality
conclusion is claimed in this pre-invocation addendum.

## Final sanitized evidence review

The reviewer read the updated `media-cost-probe-verification.md` and independently
recalculated the supplied usage and list-price arithmetic. No runtime, provider,
media, browser or additional test access was performed. The final record has no
remaining substantive evidence or claim blocker.

- Exactly three different originals were uploaded: 370 once, followed by 63 and
  372 once each. No retry of 370, composition request, model switch or additional
  media call is claimed. Two strict judgments were obtained; this is a technical
  outcome count, not a 2/3 accuracy rate.
- Content 370 remains an analysis-format failure with an unknown final answer and
  unknown substantive judgment. Its valid stream/usage does not retroactively
  establish successful relevance classification. The fence observed later on 63
  does not establish the cause of 370's failure.
- Content 63's `irrelevant` judgment distinguishes Fuqing's namesake from the
  Shenzhen target, consistent with the pre-call expectation. Its food-stall visual
  observation matches the previously recorded frame; that supports a bounded
  qualitative observation, not verification of every sign or spoken sentence.
- Content 372's `uncertain` judgment preserves the missing-location limitation and
  attributes the allegation to the source. Vegetation, railing and distant pylons
  match the recorded frame. This is not independent proof of the allegation, the
  location, or every additional model detail.
- Audio/video token counts prove reported modality processing. They are not an
  independent transcription audit or proof that the model understood all footage.
  Three selected short videos do not establish a population benchmark, general
  cost guarantee, five-platform support or a production AI pipeline.

All three input-modality subtotals and input-plus-output totals reconcile. The
aggregate is **56,021 input** (1,595 text + 53,790 video + 636 audio), **892 text
output**, and **56,913 total tokens**. Video comprises approximately 96.02% of input
tokens in this sample only. Per-sample recorded elapsed times sum to 20.124 seconds;
the harness timer includes local request preparation and answer validation, so it
is not a measurement of pure HTTP latency or total experiment duration.

Using only the main-verified standard rates, the estimates are CNY 0.178652,
0.198144 and 0.080287, totaling **CNY 0.457083**. The aggregate calculation is:

```text
(56021 - 636) * 7 / 1_000_000
  + 636 * 53 / 1_000_000
  + 892 * 40 / 1_000_000
  = 0.457083 CNY
```

The failed first call is included. Actual account charges, discounts, credits and
billing treatment were not inspected; the reviewer verified arithmetic, not a bill
or current provider pricing independently.

Main reports the backend restored and healthy, non-secret configuration/revision
unchanged, zero row differences across 14 monitoring/search tables, integrity OK,
zero foreign-key violations, and preservation of the two original Chrome tabs.
Main also reports all three owned temporary MP4 files removed after recording the
results. These are main-run preservation/cleanup checks, not reviewer database or
browser replays. The record explicitly notes port 5173 was unavailable and makes
no frontend/UI acceptance claim.

Two minor record-wording corrections were sent to main: mark the already-reported
MP4 cleanup complete instead of future-tense, and label the timings as per-sample
probe elapsed time rather than pure API latency. Neither requires another test or
paid invocation. Only this review report was appended; product source, credentials,
runtime and Git were untouched by the reviewer.
