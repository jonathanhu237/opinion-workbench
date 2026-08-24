# Technical Design

## Architecture and boundaries

The feature extends the delivered connection pipeline instead of creating a Douyin-specific
product service:

```text
React account center
  -> POST /api/v1/platform-connections/dy/attempts
  -> FastAPI global single-flight service
  -> fixed MediaCrawler --platform dy --type auth subprocess
  -> borrowed Chrome / task-owned Douyin page
  -> fresh read-only Douyin online-auth probe
  -> constant-only dy events
  -> FastAPI terminal state
  -> TanStack Query polling and platform-aware guidance
```

The boundary ends at authentication readiness. Search, detail, creator, comments, downloads,
stores, databases, explicit auth-state persistence, and account identity remain unreachable.

## MediaCrawler design

### Shared authentication protocol

- Add `AuthPlatform.DOUYIN = "dy"` and include Douyin in the CLI `auth` allowlist.
- Keep the existing protocol version, phases, exit codes, and exact three-field event schema.
- Add a small Douyin event wrapper that always supplies `AuthPlatform.DOUYIN`; arbitrary platform
  strings never reach `emit_auth_event`.

### Auth-only orchestration

`DouYinCrawler.start()` gains an early auth-only branch with the same invariants as Weibo and
Kuaishou:

1. force borrowed visible Chrome/CDP and no proxy;
2. create and register one task-owned page;
3. emit `checking` and run the fresh online-auth probe;
4. if connected, emit `connected` and return before collection;
5. otherwise emit `waiting_for_login`, open only the official visible login UI, and wait boundedly;
6. use local Cookie/LocalStorage/UI changes only as wake-up hints;
7. rerun the fresh online-auth probe;
8. emit `connected` only for an affirmative online result, otherwise `disconnected`;
9. close only registered pages in all terminal and cancellation paths.

Authentication-mode CDP failure raises the stable browser-unavailable error and never executes the
normal crawler's standard-browser fallback. Normal crawler behavior keeps its existing fallback.

### Visible login helper

Add a `visible_page_only` mode to `DouYinLogin` or an equivalent narrow helper:

- it may open the official login dialog;
- it never calls `find_login_qrcode()` or `show_qrcode()`;
- it never fills phone/SMS/password fields;
- it never invokes challenge-solving utilities;
- it waits for user-driven UI/local-state change within a bounded interval;
- slider/challenge presence remains manual and can extend only within the overall worker timeout;
- selector drift or inconclusive UI remains non-success.

The existing normal qrcode/mobile/cookie methods and manual-slider behavior remain unchanged
outside auth mode.

### Fresh online-auth probe

Introduce a separate auth-mode probe rather than redefining normal crawler `pong()` immediately:

```python
DouyinAuthResult = Literal["connected", "disconnected", "inconclusive"]

async def check_douyin_online_auth(page: Page) -> DouyinAuthResult: ...
```

Contract:

- force a fresh same-origin network-backed official page state (navigation/reload or a verified
  read-only same-origin account check);
- classify only stable authenticated and anonymous official-page signals;
- return `inconclusive` for challenge overlays, navigation failure, selector ambiguity, or schema
  drift;
- expose no account identity or raw response/page payload;
- never classify from Cookie/LocalStorage alone;
- tests mock the three result classes, while real acceptance validates current official behavior.

If implementation research cannot produce stable positive, anonymous, and inconclusive evidence,
the rollout stops and Douyin remains unavailable in the product catalog.

## FastAPI design

- Extend `AuthPlatformId` and the trusted product mapping to exact `wb | dy | ks`.
- Mark Douyin `enabled/not_checked` only after the worker probe and real acceptance gates pass.
- Reuse the current fixed command builder, one global task slot, timeout/cancellation/process-group
  ownership, event parser, transition validator, status mapping, and safe error envelopes.
- The parser must require `event.platform == active_attempt_platform`; test all mismatch directions
  involving `dy` without exposing raw child output.
- No MediaCrawler runtime imports or product database changes.

## React design

- The API schema already includes `dy`; the catalog fixture and behavior tests change Douyin from
  `coming_soon` to `enabled`.
- Reuse the existing generic platform row, mutation, polling, and `guidanceFor(display_name)` flow.
- Generalize workbench readiness copy to derive enabled platform names/counts from the catalog
  instead of hard-coding Weibo and Kuaishou.
- Keep Xiaohongshu and Toutiao disabled and truthful.

## Compatibility and migration

- No persisted schema or migration.
- Backend restart still resets every enabled connection to `not_checked`.
- Protocol version and exit codes do not change; only the trusted platform enum expands.
- Weibo and Kuaishou commands/events/tests must remain byte-for-byte compatible where applicable.
- Normal Douyin crawler qrcode viewer, mobile login, manual slider, search/detail/creator branches,
  and standard-mode fallback remain available outside `--type auth`.

## Operational and rollback considerations

- Do not enable Douyin in the product catalog until automated probe classification and real Chrome
  acceptance both pass.
- Roll back if auth mode reaches collection/store code, extracts QR material, automates a challenge,
  trusts local state as terminal proof, launches fallback Chrome, or closes a user-owned page.
- Deliver the MediaCrawler commit to the derivative remote before committing the parent gitlink.
