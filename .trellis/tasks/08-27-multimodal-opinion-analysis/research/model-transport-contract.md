# Model Transport Contract

Planning proposal, 2026-08-27. No live provider requests or private credentials used.

Scope terminology update: the revised parent removes standalone screening. The per-item decision/evidence contract below is executed only inside an explicitly requested summary operation. A later synthetic text test passed in the configuration child; media capability remains unverified. This document's provider research itself used no live credentials or calls.

## Evidence

- The [Omni guide](https://help.aliyun.com/zh/model-studio/qwen-omni) documents streaming Chat Completions, text-only output selection, `image_url`, and `video_url` inputs. Video-file input includes sound. Inline Base64 must be below 10 MB; URL input has different limits. Region/workspace and credential must match.
- The [Omni Plus model page](https://help.aliyun.com/zh/model-studio/qwen3-5-omni-plus) marks structured output unsupported. Do not assume `response_format=json_schema` will work. Its pricing distinguishes modalities; a connection check is not a free service guarantee.
- [HTTPX async](https://www.python-httpx.org/async/) and [timeouts](https://www.python-httpx.org/advanced/timeouts/) provide async streamed responses and bounded network phases. The repo already locks `httpx` transitively; promote that exact compatible library to a direct runtime dependency when implementing. The unrelated `httpx2` dev entry does not establish a runtime import contract.

## Application-Owned Decisions

These are proposed product safeguards, not provider promises.

### Destination and request

- One configured HTTPS Base URL, normalized trailing slash, then append `/chat/completions` exactly once. Reject userinfo, query, fragment, controls, non-HTTPS schemes and non-public destinations. Never derive a destination from collected/model-generated text.
- Use a backend-owned async HTTP client, TLS verification on, redirects off, environment proxy inheritance off. No automatic SDK/network retries, tool calls, function calling, search, or audio generation.
- Standard payload: configured `model`, system/user messages, `stream: true`, `modalities: ["text"]`, bounded `max_tokens`. Do not set unsupported JSON-schema mode or undocumented provider extensions. Other endpoints must accept this contract; report incompatibility instead of removing media or switching protocols silently.
- Keep a small code-owned compatibility check separate from user configuration: the initial reviewed multimedia contract is Qwen3.5-Omni. Known text-only or unknown multimedia contracts fail before media upload with an actionable unsupported/unverified-input error; a successful text test cannot enable them. Further multimodal contracts require documented formats and live acceptance, not a new user-facing provider manager. A proxy's actual model behavior still needs live validation; the name alone proves nothing.
- Text connection test uses a tiny fixed prompt and a 30-second overall deadline. Save/read/page load make zero model calls. Tests use the saved configuration; disable testing unsaved edits and ask the user to save first.
- Per-item analysis within summary generation: at most one call per uncached complete item; overall deadline 180 seconds, connect 10 seconds, read inactivity 30 seconds, output limit 2,048 tokens. Final composition output limit 4,096 tokens. Every deadline and output cap is explicit and unit tested.
- SSE decoder handles fragmented UTF-8, multiline/chunked events, empty choices, optional usage events and terminal markers. Require a complete successful finish; partial streams, refusal/tool outputs, length truncation and malformed JSON are failures. Bound total retained response text to 64 KiB and stop on overflow. Keep only final `delta.content`, never reasoning/audio/debug payloads.

### Direct media envelope

- Build typed user content from one original post: text, each verified actual image as `image_url`, and actual video as `video_url`. Use inline Base64 from bounded local files, not source-page URLs, signed media URLs, Cookies or headers. For the initial Omni path use its documented inline video data form; do not infer generic vendor compatibility.
- Initial formats: JPEG, PNG, WebP images and a self-contained MP4 video retaining its audio track. No image/video conversion, frame extraction or independent OCR/ASR. Other forms are reported as unsupported, not converted implicitly.
- At most 24 image assets and one video per post; maximum aggregate raw bytes 6 MiB and complete encoded JSON body strictly below 9,000,000 bytes. Full text is capped at 20,000 characters; exceeding a limit makes input incomplete, never silently cropped. These conservative limits bound memory, storage and request size; they are not claims about maximum provider capability.
- Media data is uploaded only within an explicitly requested summary operation. No provider File API or cloud object store is used, so no remote file ID lifecycle is introduced. This does not promise provider-side zero retention; the configured provider's own data policy applies.
- Temporary media is deleted after the owning item finishes/cancels. Retain hashes, MIME/size and coverage metadata plus bounded source text/evidence, not media bytes or source credentials. Explicit force-refresh during generation reacquires media. Reusing compatible completed evidence does not require retained files or claim that the remote post was revisited.

### Output contracts

Per-item analysis output is one JSON object, validated with strict Pydantic types and no extra keys:

```json
{"decision":"relevant","reason":"Short rationale","evidence_summary":"What the supplied post reports, including relevant visual/audio evidence"}
```

- `decision`: `relevant | irrelevant | uncertain`; reason 1–300 characters; evidence summary 1–1,000. No model-owned source IDs/URLs, risk levels or sentiment are required.
- Application adds the source ID and original link, input hash, prompt version, model/configuration revision, time and actual input coverage. Output-format failure is technical failure, not `irrelevant`; no hidden repair call.
- Summary model output: `{"overview": string, "items": [{"text": string, "source_ids": [integer]}]}`. Each paragraph/item must reference one or more supplied IDs; reject invented IDs, empty citations and malformed output. Source links are reconstructed by the backend. The overview must only summarize cited items.
- Keep model prose as escaped text, not executable HTML or trusted Markdown links. Model output never triggers a browser action, configuration change, file read or external request.

### Prompt intent

Use a versioned instruction plus the collection run's frozen rule name/terms. Ask whether the supplied content reports a public issue, feedback, dispute, incident or relevant follow-up within that scope; relevance is not equivalent to negative sentiment. A problem word is a search hint, not proof of a current negative incident. Identify resolved/historical reports as such, preserve attribution and distinguish same-name locations or insufficient evidence. Do not invent local boundaries, verify allegations as facts, or build author profiles. Source text, captions and media are untrusted evidence, including instructions visible inside them. The model must not follow such instructions.

Final composition input is relevant source text and saved per-item evidence, with immutable source IDs and coverage counts. It runs within the same manually requested pipeline, does not upload videos again and makes no second per-item analysis. Preserve uncertainty and attribution; do not turn separate posts into independent incident counts or describe resolved reports as ongoing problems.

## Failure Categories and Tests

- Map authentication, model-not-found, rate limit, provider unavailability, timeout, invalid output, unsupported input and request-too-large to constant Chinese messages. Do not retain provider error bodies, authorization headers or raw exceptions.
- Block input-incomplete items before making a billable call; keep them separate from an LLM's `uncertain` decision. UI may group both under `无法判断` while showing their distinct reasons/origin.
- Use fake transports for success, 401/403/404/429/5xx, redirect, reset mid-stream, invalid JSON/schema, oversized/empty output, malicious source instructions and unknown citations. A 200 text response is not proof of actual image/video/audio understanding.
- Later live acceptance needs small authorized text, image and audio-bearing video fixtures with facts absent from the title/cover. Record only non-secret counts/outcomes. Exact model access and quality cannot be proven during this planning phase.
