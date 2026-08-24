# Douyin online-auth probe spike

Date: 2026-08-24 (Asia/Shanghai)

## Official network signal

- A fresh, anonymous Chrome context loaded the official Douyin homepage and the official account
  SDK bundle currently maps `getUserInfo` to `GET /passport/account/info/v2/`.
- The account SDK consumes a successful account result through the `sec_user_id`, `screen_name`,
  and `avatar_url` fields. The authentication probe needs only the non-empty presence of
  `sec_user_id`; it never returns or records that value.
- A direct same-origin request with `credentials: include`, `cache: no-store`, and a unique query
  value returned HTTP 200 in the anonymous context. Its secret-free shape was
  `message=error`, `data.error_code=13`, and `data.name=account_info_error`.
- The earlier `/passport/user_info/get_sec_ts/` candidate was rejected because the official
  bundle uses it for secure timestamp material rather than account-login proof.

## Exact classification

- `connected`: HTTP success, exact official `message=success` wrapper, object `data`, and a
  non-empty string `data.sec_user_id`. The page returns only the constant `connected`; the
  identifier and raw response never cross into Python.
- `disconnected`: HTTP success with the exact anonymous result
  `message=error`, `data.error_code=13`, and `data.name=account_info_error`.
- `inconclusive`: visible official challenge, network/navigation failure, non-2xx response,
  malformed JSON, wrapper/schema drift, unknown error, or any result outside the two exact shapes.

The implementation does not read Cookie or LocalStorage in the online probe. Local login markers
are allowed only inside the visible manual-login helper to wake the follow-up network probe; stale
initial markers cannot wake it.

## Rollout gate

- Automated tests can prove the three-state boundary, fail-closed schema handling, no QR
  extraction, manual-only challenge handling, and the no-collection/page-ownership invariants.
- A real logged-in Chrome run is still required to observe the current positive official shape.
  Until that run succeeds, the backend catalog and React fixture keep Douyin `coming_soon` even
  though the trusted worker command and typed event protocol accept `dy`.
- If the real positive result is not the exact success shape above, the implementation must remain
  gated and the signal must be re-evaluated; it must not fall back to Cookie, LocalStorage, URL, or
  UI-only evidence.

## Gate outcome

- The subsequent real borrowed-Chrome run produced the exact positive classification, emitted
  `checking -> connected`, and exited normally.
- The positive gate therefore passed and the product catalog was promoted to
  `enabled/not_checked`; see `real-chrome-acceptance.md` for non-sensitive ownership counts.
