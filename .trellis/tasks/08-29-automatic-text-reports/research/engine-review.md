# Independent engine review

Reviewer: main. The engine implementer is separately reviewing C core/UI; that
review does not count as an independent review of their own engine files.

## Scope and observed boundary

Read both engine production files completely and inspected focused assertions
for exact serialized bounds, source/child partitioning, strict shape and nested
mutation, credential handling, request/reuse hashes and no-IO behavior.
Compared with the accepted `text-engine-contract.md`, parent design section 5
and the new `topic-report-guidelines.md`.

- Frozen evidence revalidation includes original accepted full text, all saved
  understanding fields, prompt/provider provenance and ready-media metadata.
  Metadata checking does not claim to reconstruct media bytes/freshness.
- Request construction uses strict compact sorted JSON and the complete exact
  system/user strings. A real escaped-text case reaches exactly 120,000
  characters while staying inside the accepted upstream text limit; one extra
  character fails. Largest-prefix partitioning preserves the unused suffix.
- Leaf union equals all admitted IDs. Overview requests contain only bounded
  child keys/overviews; the reducing tree carries the real final singleton.
  Independent tests cover 1, 8, 9, 101 and 1,001 inputs, not only one page.
- `output_digest` is a shape/integrity helper, not a graph/citation proof. The
  fresh-call contract explicitly leaves provider/graph/context reconstruction
  in core. Stored messages/hashes are never sufficient executable authority.
- Matching saved outputs are revalidated for kind, nested shape, citations,
  digest and decoded credential-bearing prose. Invalid parse/validation retains
  known usage; reused output has no historical usage field.
- Engine imports the existing encoder/budgets but performs no model, browser,
  media, file, socket, database, queue or lease operation.

## Findings and resolution

1. Initial review found whitespace-only report/initial instructions could pass
   engine prompt hashing. The implementer changed both validators to nonblank
   exact-prose checks without trimming accepted text and added regression tests.
2. Initial review found embedded JSON `true` could compare equal to source ID 1
   during call-envelope membership checking. Both judgment and leaf now require
   exact integer IDs; tests assert rejection before encoding.
3. The implementer's first focused tests exposed escaped credential leakage
   when decoded text was reserialized before checking. Final code checks each
   decoded prose field, in addition to raw-answer validation; reviewed tests
   cover plain, Unicode, HTML, percent and escaped forms with usage preserved.

No open engine-local finding at this review. Core graph proof, original-call
reconstruction, canonical reuse ownership, durable usage/cancellation and actual
API projections remain separate final integration gates, not engine guarantees.

## Validation evidence

The implementer's serialized Centaurus focused run passed Ruff, formatting and
175 tests (`0.87s`); see `engine-implementation.md` for commands and remote parity.
Main's subsequent local SHA-256 check matched all three recorded hashes:

```text
9fdb6fd7c31db41f4344e6a006fff197ecc66f966fe432c3aa00be6f8ab12e92  schemas/topic_report_engine.py
f462c5b7beb33886338c0a6586886de31a36dc5932e7ecaba009332b0a88eb2f  services/topic_report_engine.py
0dcae0390ea1dc6c9fd148f959f256809364116a0959571e2b1aed339db5a4e0  tests/test_topic_report_engine.py
```

The final merged backend gate must include this suite again after core changes.
No live model/account/media work, production data migration or Git mutation was
used for this review. Mock semantic examples do not establish model accuracy.
