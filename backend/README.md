# OpinionWorkbench API

The product API is an independent Python package. Development instructions live in
the repository root README.

## Model output recovery

- Structured tasks on the verified DashScope `qwen3.5-omni-plus` endpoint use
  `response_format: {"type": "json_object"}`. Other providers and the plain-text
  connection test retain their existing protocol; JSON mode is not schema validation.
- Final answers are parsed strictly first. `json-repair` is a fallback only for
  bounded, balanced objects whose tokens remain identical except for commas and
  string delimiters. Missing content, duplicate keys, ambiguous values, surrounding
  prose and truncated objects are rejected. SSE transport data is never repaired.
- All repaired objects still pass the existing schema, credential and citation
  checks. A JSON/schema/citation failure allows one additional model call within
  the same initial-analysis or report node, with the same frozen input. Transport,
  authentication and credential-leakage errors are not automatically retried.
- Database v29 adds retry accounting columns without rewriting historical rows.
  Both requests are counted, known token usage is summed, and missing provider
  accounting stays incomplete. Cancellation/restart does not automatically resume
  the retry or reacquire media. No raw failed model output is persisted.
