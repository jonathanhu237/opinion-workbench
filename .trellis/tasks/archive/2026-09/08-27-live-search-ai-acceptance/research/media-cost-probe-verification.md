# Real-Video Cost Probe — 2026-08-28

## Scope and preflight

The user explicitly approved a small sample of already collected sources after
discussing video token cost. See `media-cost-probe-plan.md`. This is an isolated
experiment, not production enrichment/summary pipeline acceptance.

- Existing saved non-secret settings: revision 1, `qwen3.5-omni-plus`,
  `https://dashscope.aliyuncs.com/compatible-mode/v1`. The public GET succeeded.
- No model switch, configuration edit, new search, collection mutation or rule edit.
- Before the probe: 486 global contents, 50 runs, 8 batches, 1 rule. Every run and
  batch is terminal; SQLite integrity OK and zero foreign-key violations.
- Centaurus is reachable. Source-only fake-test checks belong there; media and
  credentials remain on the Mac. No key was copied from conversation or printed.

## Actual input acquisition

Four stored Douyin originals were inspected in one newly owned Chrome tab. Three
had usable self-contained media. Read only the rendered post heading and actual
video element; no browser-storage or hidden-state extraction. The initial full
page snapshot incidentally included surrounding comments/recommendations; none of
those are in the model input or persisted report. Subsequent reads were narrowly
scoped to the heading/player.

The three observed HTTPS media URLs shared a Douyin CDN host. Downloaded each once
with no Cookies/Authorization headers, proxies or redirects, using a public pinned
IP, verified HTTPS and a 6 MiB/30-second bound. Each returned HTTP 200. Temporary
download-address files were removed immediately after successful download. The AI
input uses original file bytes, never those addresses or browser credentials.

| Content | Canonical source | Duration | Bytes | Video | Audio |
| --- | --- | ---: | ---: | --- | --- |
| 370 | https://www.douyin.com/video/7618140825117084968 | 35.805011 s | 3,922,868 | HEVC, 720×1280 | AAC, 35.805011 s |
| 63 | https://www.douyin.com/video/7540135476923288832 | 40.566667 s | 4,020,808 | HEVC, 720×1280 | AAC, 40.517007 s |
| 372 | https://www.douyin.com/video/7678523128784384869 | 15.1 s | 4,432,193 | HEVC, 576×1024 | AAC, 15.046009 s |

Container/stream details were checked with local `ffprobe`, without re-encoding,
frame extraction, ASR, silent clipping or sending files to Centaurus. All media
files and the input manifest are mode 0600 inside an owned mode-0700 ignored
runtime directory. Total duration: 91.471678 seconds.

Content 371 was not downloaded or sent to the model: its player reported 119.584
seconds and a blob source, outside this probe's 90-second/direct-MP4 bound. This is
not proof that the platform or model cannot support that source in a later design.

Input hashes:

- 370: `b69f4907157cfbeb4eb894ddcc7036d2e30dd79bc6ac38768bc5866eba08c059`
- 63: `dee321ed7ddc826a679f77313a7c0a3a2fa0305507c1569bce875f053ace3277`
- 372: `428ba38c485ee611399ca3819f2010784be4ce03a08dd088e455268819c31821`

The only owned inspection tab was closed. Both pre-existing Chrome tab IDs remain;
no login, browser permission or platform challenge was completed automatically.

## Independent source expectations (before model invocation)

- **370:** Caption explicitly names Pingshan/Longtian and a hotel-side poultry-pen
  nuisance with enforcement follow-up. It is dated 2026-03-17, not a newly occurring
  incident. An observed frame shows people on outdoor steps and an enforcement
  instruction subtitle. Expected relevant historical issue/follow-up, not proof
  of ongoing pollution or independently established wrongdoing.
- **63:** Caption explicitly names Fuqing's Longtian and a positive hometown vlog,
  dated 2025-08-19. An observed frame shows a market/food stall. Expected unrelated
  to Shenzhen's target locality, despite the shared name.
- **372:** Caption alleges wastewater discharge but names no target locality,
  dated 2026-08-27. An observed frame shows waterside vegetation, a railing and
  distant pylons. Location remains unproven unless the supplied audio/video itself
  establishes it. A complaint alone is not enough for a confident target-area label.

These observations are qualitative and do not independently verify every spoken
word, every frame, a location boundary or the truth of allegations.

## Model execution and usage

Initial isolated harness gates passed: 28 fake tests on Centaurus in 0.17 seconds,
local format/lint passed (implementer), main read-only validation accepted all three
inputs, and independent source review found no remaining blocker. Shared AI client
and settings-service source hashes matched between Mac and Centaurus.

The idle production backend PID 228 was gracefully stopped; application shutdown
completed and port 18000 had no listener. Only then was the local standalone
configuration owner used. No credentials left their service-owned call path.

### First invocation — content 370 only

- One HTTP attempt, 7.091 seconds, provider model matched the configured model.
- Valid completed text stream and usage reached the probe, but local final-answer
  JSON/schema validation failed (`probe_invalid_response`). No repaired/repeated
  call was made and the loop stopped before contents 63/372.
- Final answer text was not retained by the original harness; therefore the exact
  format mismatch and the model's substantive judgment are **unknown**. Do not
  infer a particular fence/schema issue or claim a successful relevance judgment.
- Actual usage: input 22,230 (text 597, video 21,386, audio 247), text output 292,
  total 22,522 tokens. Positive audio/video usage establishes provider metering,
  not that every spoken word/frame was understood accurately.
- Standard Beijing list-price estimate: `(22230 - 247) * 7 / 1e6 + 247 * 53 / 1e6
  + 292 * 40 / 1e6 = CNY 0.178652`. Source:
  https://help.aliyun.com/zh/model-studio/model-pricing (checked 2026-08-28).
  This is not the account's actual bill; credits, caching/discounts and billing
  treatment were not inspected.
- Production backend restored immediately as PID 6877, port 18000, while the
  isolated probe's diagnostic recording is corrected offline. A fresh manifest
  contains only original remaining IDs 63/372; content 370 will not be retried.

### Remaining original samples — 63 and 372, once each

The diagnostic-only revision passed **38 fake tests** on Centaurus in 0.26 seconds,
plus Ruff check/format. An initial remote lint run caught two import-order issues
because the backend working directory classifies the package as first-party;
main changed only those imports locally, re-synced and repeated all gates green.
Independent review passed; read-only validation accepted exactly two inputs.

Final harness SHA-256:
`d0db002264dbbc071d4a89bcda6417b1ae273361c411e3344a3afc631ce5f358`.
Final tests SHA-256:
`adae7d1a25a93d99653c4a4695474a0c67781e164e8ff237cddcbf29a1f470fd`.

After graceful shutdown of backend PID 6877 and confirming no listener, the second
private invocation sent exactly two requests and completed both. This was not a
retry of content 370. Both provider model projections matched the saved model.

| Content | Result | Input text | Input video | Input audio | Total input | Text output | Total tokens | Per-sample probe elapsed | Standard-price estimate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 370 | Local output validation failed; judgment unknown | 597 | 21,386 | 247 | 22,230 | 292 | 22,522 | 7.091 s | CNY 0.178652 |
| 63 | `irrelevant` | 552 | 23,762 | 282 | 24,596 | 325 | 24,921 | 7.398 s | CNY 0.198144 |
| 372 | `uncertain` | 446 | 8,642 | 107 | 9,195 | 275 | 9,470 | 5.635 s | CNY 0.080287 |
| **Total** | **3 attempts; 2 validated judgments** | **1,595** | **53,790** | **636** | **56,021** | **892** | **56,913** | **20.124 s** | **CNY 0.457083** |

Prices use the verified Beijing standard rates: text/image/video input CNY 7 per
million tokens, audio input CNY 53, text output CNY 40. The total includes the first
local-validation failure. Actual charges/credits were not read and are not claimed.
Video tokens account for approximately 96% of the input in these three samples;
this small duration/resolution-specific sample is not a general cost guarantee.
Elapsed time includes local request encoding and final-answer validation, not only
provider/network time. Independent final evidence/arithmetic review passed; see
`media-cost-probe-check.md`.

Validated judgments and qualitative review:

- **63 — unrelated namesake:** the model correctly distinguished Fuqing's Longtian
  from Shenzhen/Pingshan's target. It reported street/market/food-stall visuals and
  a hometown voiceover, rather than merely repeating the title. The food-stall
  observation is consistent with the independently inspected frame. Other exact
  signs/transcriptions were not independently verified in full. The model retained
  the 2025 source date. This response had an exact enclosing JSON code fence;
  deterministic removal yielded a valid strict object. That finding does **not**
  establish why the earlier content 370 response failed.
- **372 — uncertain locality:** the model reported vegetation, dark water, a
  concrete railing and distant electrical infrastructure, consistent with the
  inspected frame. It attributed the discharge allegation to the source and said
  no locality evidence connected it to the monitored area. It did not invent a
  Shenzhen incident. This response was valid JSON without fence removal. No claim
  is made that all 15 seconds were independently audited for every possible sign.

No summary/composition request, automatic repair request, model switch, screenshot
upload, separate audio request or repeated video upload occurred. These results
establish a useful small-sample multimodal experiment, **not** an accuracy rate,
five-platform media acceptance, a production cache, or an integrated AI report UI.

## Preservation and closure

- The production backend is restored as **PID 8006**, exec session **31137**, port
  **18000**. Health is OK and the non-secret AI projection remains identical,
  including revision 1. No model call was made by health/settings checks.
- Compared all 14 monitoring/search tables row-for-row with a fresh private local
  backup: zero added or removed rows. Integrity OK; zero foreign-key violations.
  The 486 contents, 50 runs, 8 batches and original rule remain intact.
- Source files changed only under this verification task. Existing unrelated dirty
  product/submodule changes were preserved. No commit, push or archive was performed.
- All three owned temporary MP4s were deleted after the reports were saved; only
  private model reports/input metadata and the private backup plus this sanitized
  result record remain. No original platform post or collected row was deleted.
  The owned Chrome inspection tab was already closed and both original tabs kept.
- Port 5173 was found unavailable during later health checks; no frontend/tunnel
  process was stopped or restarted by this probe, and no UI acceptance is claimed.

## Experiment lesson

The first harness conflated invalid final JSON and invalid structured fields and
discarded the completed answer. That prevented diagnosing the first mismatch
without another paid call. The correction separates local output stages, retains
bounded secret-checked plain diagnostics, and tests exact fence handling without
semantic repair. Valid usage remains recorded even when local analysis validation
fails. Product AI contracts are unchanged; this task-local observation should inform
the later summary implementation review rather than being treated as shipped code.
