# Recovery UI Evidence and Constraints

## Existing owners

- `frontend/src/routes/collection-batch-detail.tsx:151`: `BatchRail` renders the latest
  attempt's progress, counts and result link; `AttemptHistory` retains older run links.
  Resuming with only a suffix would make these latest-only counts look like lost results.
- `frontend/src/routes/collection-batch-detail.tsx:256`: the page owns continue/cancel
  mutations and nearby feedback. Extend this boundary rather than adding a second queue.
- `frontend/src/routes/collection-batch-detail.tsx:386`: the paused card assumes a visible
  CAPTCHA and offers only continue/cancel. Replace that assumption with cause-specific copy.
- `frontend/src/lib/api/search-batches.ts:43`: strict item decoding currently requires
  `manual_challenge_required` for every paused item. It also assumes queued items have no
  latest attempt, which must be reviewed for the continue-to-run transition.
- `frontend/src/lib/api/search-batches.ts:117`: aggregate decoding counts only
  completed/failed/cancelled as terminal and enforces exactly one current paused item.
  Keep those consistency checks, extending them deliberately for operator skips and
  broader pause reasons rather than weakening validation.
- `frontend/src/hooks/use-search-batches.ts`: resource reads do not start browser work;
  polling is enabled for queued/running only, mutations invalidate authoritative state.
- `frontend/src/routes/collection-run-detail.tsx:72`: `ResultRecord` owns existing result
  presentation; XHS opens through a relationship-checked API while other platforms use
  canonical links. Reuse this presentation for aggregated platform results.

## Target interaction (proposal for final review)

Keep the existing batch-detail page, palette, typography and platform rail. At a pause,
show one compact actionable card:

```text
采集已暂停 · 小红书
已完成 16 / 20 个搜索词
当前搜索词：<the stored term, not raw error text>
平台要求安全验证。请在谷歌浏览器中查看是否有验证提示。

[打开平台]  [继续采集]  [跳过此平台]  [取消批次]
```

The example is an illustrative state, not a claim that a real CAPTCHA exists.
Copy must distinguish:

- Login required: open the official page and sign in, then explicitly continue.
- Challenge signal: look for the platform's actual verification entry; if absent, say
  that opening the page cannot guarantee a verification flow is available.
- Browser unavailable: restore the existing Chrome/debug connection; no copied profile
  or new automation browser as a silent fallback.
- Block/rate limit: stop; tell the user the platform is restricting access. No automatic
  retries, countdown reattempts, or repeated request loops.
- Structure/internal/timeout: preserve the technical category and offer retry/skip,
  without implying another login will repair the adapter.

An `opened` response means only that an official page was opened/focused. It does not
mean logged in, verified or recovered. Continue starts one explicit bounded attempt;
the real collection outcome decides whether to advance or pause again.

## Results, cache and accessibility

- Show batch-item aggregate counts across attempts, not just latest-run counts. Keep
  an explicit latest-attempt/history link for diagnostics. Use `已结束` rather than
  `已完成` when a header count includes skipped/failed platforms.
- Reuse existing result cards in an expanded platform-result section of batch detail;
  URL search params own the selected platform, kind and offset. Do not add a new sidebar
  module or unrelated visual redesign. Server aggregate queries own deduplication.
- Keep query keys qualified by batch ID/item/filter/offset. Continue/skip/cancel
  invalidates batch/detail/history/results; no durable recovery point in React state.
- Use existing Shadcn/Base UI `Button`, `Card`, `Badge`, `Skeleton` and semantic tokens.
  Normal navigation links remain links; browser actions are buttons with explicit text.
- Lock competing actions while one request is pending, give the active action a loading
  label, and keep a bounded cancellation path. Never mark successful recovery optimistically.
- Show action feedback near the recovery card via `aria-live`; failures also use
  `role="alert"` where appropriate. Preserve keyboard focus, visible focus and mobile
  wrapping. Stale-tab conflicts refetch the current state instead of replaying mutations.

## Local skill research

`ui-ux-pro-max` was used only for targeted interaction guidance:

- `error recovery feedback --domain ux`: verified matching rows were Error Recovery
  (clear next steps), Error Feedback (nearby visible failure), and Error Messages
  (live-region announcement).
- `button loading disabled --stack shadcn` first returned mostly off-target skeleton/
  dialog suggestions; these were not adopted as loading requirements. One narrower
  retry, `button accessibility --stack shadcn`, matched semantic native/Shadcn controls
  and preserving component focus behavior.
- `frontend-design` informed concise, operator-facing action labels and omission of
  decorative status text. Its generic visual-experiment guidance does not override the
  user's explicit request to retain this application's current Shadcn UI and palette.

No dependency, component, palette, font or product source was changed during research.

## Implementation acceptance (2026-08-28, synthetic only)

The completed UI uses the existing components and palette. A real in-app browser exercised the
built frontend against the isolated FastAPI/synthetic-worker preview: open-only feedback, 6/8 to
8/8 continuation, next-platform login pause, all-attempt result union, history, filters and skip.
The final view retained three results, two historical attempts and a truthful partial-failure status.
Browser warnings/errors for that preview were empty. Unit interaction tests cover keyboard/focus,
wrapping action rows and cancellation during a pending show request. No real CAPTCHA, real platform
resume or mobile-device acceptance is claimed. Detailed evidence is in
`implementation-verification.md`; production runtime and existing batch 8 were not changed.
