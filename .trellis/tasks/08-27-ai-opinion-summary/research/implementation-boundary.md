# Integration Boundary — 2026-08-28

The user approved saving the model's understanding of each post and reusing that
text for final composition. This is attributed content analysis, not verification
that an allegation is true or forensic evidence.

## Smallest behavior gap

Configuration and bounded media acquisition exist, but `main.py` does not construct
the enrichment service, there is no summary runner/storage/API, and collection
results expose no summary action. Connect these existing boundaries for one manual
full-run operation. A one-item Douyin case is the first acceptance sample, not a
new public source-selection mode or silent reduction to the visible UI page.

## Ownership

- Backend transport: extend `services/ai_client.py` compatibly with validated usage;
  add one bounded typed model-input/output owner and focused transport tests.
- Backend product: additive v11 summary run/item migration, repository, service,
  strict schemas/router, and lifespan wiring. Preserve all dirty v10 recovery code.
- Frontend: one summary section within collection-run detail, API decoder and
  behavior tests. Keep existing shadcn components, tokens, fonts and source-opening
  behavior. Use Chinese labels `内容分析` / `分析结果`, not forensic `证据` terminology.
- Main: task coordination, API contract alignment, source-only Centaurus sync,
  quality gates, browser QA and verified spec updates.

## Explicit exclusions

No fork/collector changes, new browser controller, new settings/provider manager,
automatic paid requests, separate screening UI, batch-wide report, charts,
notification workflow, pricing panel, or commit/push. Do not migrate or copy the
user's runtime into remote tests. Provider acceptance remains separately authorized.

## Proof required

Fake boundaries must prove one item uploads media once, final composition is text
only, compatible reuse makes zero new item calls, incomplete input makes no model
call, failures preserve prior analysis, and refresh/restart never starts AI work.
Run complete backend/frontend frozen gates on Centaurus and review integration.
Record live media/AI acceptance as pending unless actually performed. The media
child remains in progress; checked fixtures are not five-platform live support.

## Confirmation race correction

The start request includes `configuration_revision` from the configuration shown
in the confirmation. The stable AI lease must reject a changed revision before
media/model work. UUID idempotency also binds this revision. This closes a
confirm-to-submit race without adding a new user setting or changing the approved
provider-disclosure behavior; silently sending to a newly edited destination is
not acceptable.
