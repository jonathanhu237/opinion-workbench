# Design — Plain-Language UI Copy

## Scope and Boundaries

This is a frontend-only content pass. Route components continue to own page copy, and existing
frontend presenter/error helpers continue to own shared status text. No new localization layer,
copy registry, dependency, route, API field, or backend message contract is introduced.

The audit boundary is all product-visible Chinese or English copy under `frontend/src/routes/` and
`frontend/src/app/`, plus text returned by frontend presenter/error mappings. Test and fixture text
is changed only when required to verify product behavior.

## Copy Decision Rubric

Apply these decisions in order to every candidate:

1. **Delete** when the sentence repeats visible information or explains an internal mechanism.
2. **Keep and shorten** when the user needs the information to interpret the current state.
3. **Keep outcome plus action** for errors and recoverable blockers.
4. **Keep consequence before confirmation** for collection, model use, scheduling, retry, and
   deletion.
5. **Keep evidence limits** when removing them could turn uncertainty into an apparent fact.

This order prevents mechanical synonym replacement. For example, the initiating workbench detail
is deleted because its title and attention cards already explain the state; it is not replaced with
`恢复正常后，这条提醒会自动消失`.

## Terminology Direction

| Internal wording | User-facing direction |
| --- | --- |
| `归属`, `健康状态`, `投影` | delete, or name the affected task/platform directly |
| `冻结意图`, `冻结范围` | `本次任务设置`, `本次分析内容` |
| `修订` | `版本` when the number is useful; otherwise omit |
| `运行快照` | omit; show the actual saved time/settings instead |
| `已保存产物` | `结果` or the direct link label |
| `文字判断` | `相关性判断` |
| `报告合成` | `生成报告` |
| `未覆盖` | `未分析` or a more precise evidence status |
| `固定工作流` | `处理流程` where the concept is useful |

These are semantic directions, not blind global replacements. Existing model-generated text and
backend-provided user messages are not rewritten without confirming their UI ownership.

## Page Groups

1. **Workbench:** remove internal duty-detail narration, redundant report explanations, and mixed
   English labels; keep stale/error/action states.
2. **Automation:** simplify task editor help, run history, retry confirmation, stage detail, version
   and result labels; retain schedule/model/retry consequences.
3. **Results and reports:** rename evidence/report progress in ordinary language, shorten empty and
   failed-state explanations, and preserve uncertainty/source limitations.
4. **Collection and platform accounts:** remove no-op reassurance, keep login/CDP/manual-action and
   retry guidance.
5. **Monitoring and AI settings:** keep form instructions only where they affect generated search
   terms, credentials, provider calls, or validation.

## Compatibility and Risk Controls

- JSX structure may be simplified by removing paragraphs, but controls, accessible names, live
  regions, and focus behavior remain unchanged.
- Tests assert behavior and visible meaning rather than old implementation terminology.
- If a piece of copy is the only explanation of cost, external side effects, destructive action,
  evidence limits, or recovery, it stays.
- If simplifying a phrase would merge distinct backend states, retain separate user-facing labels.
- No global search-and-replace is used; each occurrence is reviewed in its page context.

## Validation

Run the full frozen frontend gate and browser-check representative high-density surfaces. Search
the finished product source for the banned internal-language phrases, manually review any remaining
occurrence, and document why it is user-necessary or remove it.
