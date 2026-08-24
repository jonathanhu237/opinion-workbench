# Toutiao account connection offline validation

Date: 2026-08-24 (Asia/Shanghai)

## Scope and baseline

- Parent baseline revision: `d639dcfb0d4b1d55068a64f77a3a2c9ed1de0aa9`.
- MediaCrawler baseline revision: `f23411e9569be78b9be88be10e5153dfafcb379e`.
- This validation covers implementation and automated tests only. It did not start a browser, use
  a real account, commit, push, update the submodule pointer, modify React, or promote the Toutiao
  product catalog entry.

## Implemented offline contract

- The typed authentication platform and CLI allowlist now include exact platform `toutiao`, while
  retaining all authentication-only safety overrides.
- Toutiao `auth` has a separate borrowed-Chrome/CDP path with a constant platform event helper,
  one immediately registered task-owned Page, fresh official-page tri-state DOM proof, mandatory
  post-login recheck, fail-closed CDP startup, and owned-page-only cleanup.
- The authoritative positive DOM signal excludes generic content-author and profile anchors. Its
  legacy branch requires a visible `data-e2e="user-avatar"` inside page chrome and an interactive
  non-content-profile control. Its current-site branch requires a visible image inside a
  banner-scoped anchor with `role="button"` and `aria-haspopup="true"`. The boolean DOM snapshot
  verifies its trusted origin in the same execution context, while Python checks the Page URL
  before and after evaluation. Live-DOM selector evidence is recorded separately; the exact
  product-worker positive/ownership gate remains mandatory.
- The borrowed-browser login guard retains the current visible official page and performs no
  navigation, login-entry click, Cookie injection, QR extraction, input, or challenge action.
- Toutiao `search` remains a separate fresh standard visible-context path with optional
  `BrowserAuthStateStore`, distinct Auth/Search Pages, and its existing search/store behavior.
- FastAPI recognizes `toutiao` only as a trusted worker/protocol platform. The catalog entry
  remains `coming_soon`, and its POST endpoint still returns `platform_not_available` without
  launching a worker.
- Protocol tests cover every one of the 12 ordered foreign-event pairs among
  `wb | dy | ks | toutiao` and verify that unrelated platform state is unchanged.

## Automated results

- MediaCrawler focused auth/search/CDP suite: `119 passed`.
- MediaCrawler maintained offline suite under `tests/`: `309 passed`; one existing SQLAlchemy
  deprecation warning was reported.
- MediaCrawler changed-scope compilation: passed.
- MediaCrawler new-file copyright header check: passed.
- Backend Ruff format check: passed.
- Backend Ruff lint: passed.
- Backend full pytest suite: `75 passed`.
- Parent and MediaCrawler `git diff --check`: passed.

## Independent check follow-up

- The review closed a trusted-origin navigation race, made content-profile and hidden avatar
  candidates explicitly non-positive, and strengthened the manual-flow sentinel so any browser or
  context interaction fails the test.
- The review synchronized the executable platform-connection spec to exact
  `wb | dy | ks | toutiao` and reconciled the design with the borrowed-auth no-click behavior.
- Post-fix focused auth/search/CDP suite: `146 passed`; the existing SQLAlchemy deprecation warning
  was reported.
- Post-fix maintained offline suite under `tests/`: `336 passed`; the same existing SQLAlchemy
  deprecation warning was reported.
- Post-fix full upstream repository suite: `345 passed`, `8 skipped`, `6 failed`, and `4 subtests
  passed`. The six failures are the unchanged Redis-dependent proxy/cache integration tests; the
  sandbox rejected access to `127.0.0.1:6379` before this task's code was exercised.
- Post-fix backend Ruff format/lint passed; the full backend suite reported `75 passed`.
- Post-fix changed-scope compilation and parent/MediaCrawler `git diff --check` passed.

The broader upstream MediaCrawler tree also contains environment-dependent tests under `test/`.
Its first failing case attempted to connect to a local Redis service on loopback and was rejected
by the sandbox before exercising this change. The maintained offline suite above is fully green;
the Redis-dependent integration gate was not altered or bypassed.

## Rollout gate resolved after this check

- Real Chrome diagnostics were performed after this offline check; see `live-dom-diagnostic.md`.
- The exact MediaCrawler worker later completed a positive run once the required Chrome debugger
  approval was granted: `waiting_for_approval -> checking -> connected`, exit `0`, owned-page
  cleanup, and survival of the borrowed browser/context. See `real-chrome-acceptance.md`.
- Because that positive ownership gate passed, the backend catalog and generic React
  fixtures/tests were promoted from three to four enabled platforms. Only Xiaohongshu remains
  `coming_soon`.
- The statement below this file's original writing — that the catalog entry remains `coming_soon`
  and its POST returns `platform_not_available` — describes the pre-gate state only. The delivered
  catalog now returns 202 for `toutiao`.
