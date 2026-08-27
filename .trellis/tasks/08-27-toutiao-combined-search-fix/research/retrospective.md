# Bug Analysis: Toutiao Delayed-Render False Failure

## 1. Root Cause Category

- **E — Implicit assumption:** one DOM snapshot after a fixed 1.5-second delay assumes the official
  search page has rendered its main results. A coherent but still-pending page violates that
  assumption without proving selector drift or an empty search.
- **D — Test coverage gap:** existing static snapshots did not exercise delayed main-container or
  delayed result rendering through the real snapshot script.
- Confidence is high for this independently reproduced defect: both routed real-browser cases
  failed at the original client's structure checks and pass after bounded readiness observation.
  Historical run 34 remains unexplained; unmodified live run 43 succeeded. That evidence argues
  against claiming a deterministic current selector/URL regression, but does not identify the
  historical failure's exact cause.

## 2. Why Fixes Failed

No speculative production fixes were attempted before the failing regression was established.
The first patched test run reached its result assertions but exposed a separate test-fixture
encoding error: its synthetic HTML response omitted a UTF-8 declaration. Declaring the response
charset corrected the fixture without changing production parsing or readiness behavior. The
earlier red failures happened at the structure check before this title assertion.

The remote host initially lacked a test browser; a separate managed test-only browser was
provisioned instead of accepting skipped browser coverage or exporting the user's Chrome profile.

## 3. Prevention Mechanisms

| Priority | Mechanism | Action | Status |
| --- | --- | --- | --- |
| P0 | Runtime boundary | At most 21 reads, 20 additional waits; one navigation only; explicit terminal states and origin checks | Implemented |
| P0 | Test coverage | Real routed delayed DOM, exact bounds, terminal near-misses and cancellation/owned-page cleanup | Passing on Centaurus |
| P1 | Documentation | Record bounded readiness, non-retry semantics and historical-evidence limits in existing backend specs | Updated |
| P1 | Review | Distinguish synthetic counterfactual proof from a live historical failure; report skipped tests and fixture defects honestly | Independent review passed |

## 4. Systematic Expansion

Other browser-driven operations can encounter asynchronous rendering, but no evidence here
authorizes changing their waits or parsers. Do not introduce a generic retry framework or
cross-platform fallback. Future platform repairs need their own failing evidence and safety
boundaries. Publication-time ordering remains a separate requested follow-up.

## 5. Knowledge Capture

- [x] Update `product-search-guidelines.md` with the shared client's exact readiness contract and
  real-browser regression requirements.
- [x] Update `browser-search-adapter-guidelines.md` so pending DOM observation is not confused with
  forbidden navigation retries or false empty success.
- [x] Keep this focused repair task and sanitized verification evidence; no raw page dumps, tokens,
  credentials or runtime database copies enter versioned artifacts.
- No template tree exists in this application repository; template synchronization is inapplicable.
  Commit/push/archive remain deferred to the user's delivery request.
