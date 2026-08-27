# Model API Options

Planning research checked against official documentation on 2026-08-27. No credential was copied into tools or project files, no platform media was uploaded, and no paid API request was made.

## User-Confirmed Availability

The user has Qwen and DeepSeek APIs and confirmed Alibaba Cloud as the Qwen provider. Omni model entitlements and deployment region remain unknown. Do not infer access to every Qwen model from having an API account.

A credential shared in chat must not be copied into project files, logs, tools, or remote synchronization. The user was advised to revoke it and create a replacement. Credential replacement does not block planning; later live validation should use local secret configuration, not a key posted in conversation.

## Qwen

Alibaba Cloud documents Qwen3.5-Omni as accepting combined text, image, audio, and video inputs, including audiovisual understanding. Its guide distinguishes this from Qwen3-Omni-Flash, which permits text with only one other modality per request. The `qwen3.5-omni-plus` model page identifies Alibaba Cloud Model Studio as its inference provider.

Sources: [Qwen-Omni guide](https://help.aliyun.com/zh/model-studio/qwen-omni), [qwen3.5-omni-plus model](https://help.aliyun.com/zh/model-studio/qwen3-5-omni-plus).

Planning inference: a Qwen3.5-Omni model is a suitable candidate for the requested single-model workflow, subject to the user's actual API access and validation. Do not generalize its capabilities to all Qwen models or gateways.

## DeepSeek

The reviewed DeepSeek Chat Completions schema documents user-message content as text. Its Responses API guide explicitly excludes image/file inputs and notes that image parts can become placeholder text rather than producing an error. A successful HTTP response therefore does not prove that media was understood.

Sources: [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/), [Responses API compatibility](https://api-docs.deepseek.com/guides/responses_api/).

Planning inference: these official APIs are not a replacement for the required direct multimodal input. DeepSeek could be considered for a separate text-only summary later, but adding a second provider now is unnecessary for the user's stated simplicity goal. This does not assert anything about third-party preprocessing wrappers or unrelated open-source models.

## Proposed Direction and Verification Boundary

- The user subsequently requested editable API Key, Base URL, and model name. Do not hard-code the Qwen recommendation or restrict configuration to one brand.
- Recommend an accessible Qwen3.5-Omni model as the first audiovisual validation target. The application should use the saved model configuration; this recommendation is not a mandate to use Qwen forever or to add a separate DeepSeek summarization integration.
- The user approved one configuration shared by assessment and summary, including save and basic connection-test actions. Configurable fields alone do not establish support for arbitrary provider protocols or model capabilities.
- Documentation-level protocol, inline limits, structured-output restriction and request lifecycle are now captured in `model-transport-contract.md`. It distinguishes provider facts from conservative application limits; no File API or cloud file hosting is planned.
- Exact account entitlement/region, delivered soundtrack and real model interpretation remain live acceptance gates, not unresolved architecture questions. Do not silently substitute a cover image or visual-only processing.
- Backend secret storage and destination binding are specified in the parent design. No secret was needed for this planning research.
