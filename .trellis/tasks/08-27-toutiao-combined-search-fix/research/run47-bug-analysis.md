# Bug Analysis: Mature external-only Toutiao results

## 1. Root Cause Category

- **E — implicit assumption:** a successfully rendered main result page was expected to contain
  at least one allowlisted Toutiao content link or a literal no-results message. The actual public
  search page can instead be complete and contain only external results.
- **D — test coverage gap:** the readiness tests covered delayed rendering, explicit empty and
  malformed pages, but not a completed external-only result page with the actual auxiliary header.
- Strong evidence is the unchanged script's zero-candidate/non-empty state on the exact failed
  query, followed by two real-DOM synthetic regressions failing at the expected structure error.
  The current defect is confirmed; the uncaptured historical run 47 DOM remains unknown.

## 2. Why the Earlier Repair Did Not Cover This

The earlier bounded-readiness repair handled a different demonstrated condition: a page still
rendering. Reading a mature external-only page 21 times cannot create an allowlisted candidate
or an explicit empty message. Increasing the delay would therefore not fix this observed state.
This does not establish that the two historical failures had the same cause.

## 3. Prevention Mechanisms

| Priority | Mechanism | Specific action | Status |
| --- | --- | --- | --- |
| P0 | Runtime contract | Strict external-only completion proof; final existing read only | Implemented |
| P0 | Regression | Real DOM positives plus loading, malformed, unsafe, late-result and safety cases | 98 parser tests passed |
| P0 | Scope safety | Never follow/persist external targets or broaden the allowlist | Preserved |
| P1 | Documentation | Executable predicates in product-search and browser-search specs | Updated |
| P1 | Live validation | One normal product query with private backup and history comparison | Run 53 completed; 14 original relations preserved |

## 4. Systematic Expansion

- Distinguish “no matching platform content” from “no page data” and “page failed to load”.
- Related-search navigation and sidebar hot lists are not result titles. The exact known
  anchorless auxiliary heading is excluded; arbitrary anchorless headers still fail closed.
- Existing XHS empty/exhaustion handling is a separate contract, not a reason for a new shared
  fallback. No other adapter, public protocol or database change is justified by this evidence.
- Reproduce a precise observed state before changing selectors or timeouts; retain a tests-first
  red gate and honest limits on claims about historical failures.

## 5. Knowledge Capture

- [x] Update `.trellis/spec/backend/product-search-guidelines.md`.
- [x] Update `.trellis/spec/backend/browser-search-adapter-guidelines.md`.
- [x] Preserve bounded evidence, red/green results and frozen source hashes in this task.
- Template synchronization is not applicable: this application repository has no Trellis source
  template tree. Source-only synchronization to Centaurus remains required.
- Git delivery was deferred during debugging and is now separately authorized in `run47-delivery.md`;
  the retrospective skill itself does not commit or archive anything.
