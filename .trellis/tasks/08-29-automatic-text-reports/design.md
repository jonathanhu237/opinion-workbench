# Design C: Automatic Text Reports

Status: implemented and accepted with checked A/B. Parent `../08-28-collection-report-decoupling/design.md`
sections 2–3, 5 and 7–8 are the authoritative report contract. Depends on A and B.
Final isolated evidence is in `research/full-check.md` and
`research/browser-acceptance.md`; live activation and commit remain separate.

## Ownership

Own `topic_reports` backend models/repositories/services/API and frontend
client/report history/source/section views; next additive report migration;
event consumer and shared lifecycle/router integration after A/B finish.
Reuse old strict JSON/citation/usage/transport helpers, keeping legacy responses
and source opening intact. Do not modify stage-one acquisition to implement reports.

## Contracts

- Idempotently consume each normally settled initial-analysis job event once.
  Freeze its successful attempt text, failures, source origins and inherited
  prompt/provider intent. Later arrivals do not expand its input.
- Read only saved text. Every ready source gets a bounded text judgment; only
  relevant sources enter substantive synthesis. Uncertain and technical failure
  are separate outcomes, never fabricated unrelated decisions.
- Partition relevant sources into leaves of <=8 and <=120,000 serialized input
  characters including prompts; retain existing per-call output/deadline/byte
  guards. Validate leaf citations cover its admitted relevant membership.
- Save all leaf sections. A <=8-child bounded overview tree reduces them into
  one logical report without dropping detailed evidence or inventing source IDs.
  Record exact input hashes, compatibility, usage and failures at each node.
- Empty initial evidence uses no model; zero relevant evidence uses no composition
  call. Technical failures retain a failed report and inspectable partial draft.
- Retry is a new version using compatible saved nodes; changed report instructions
  invalidate only downstream judgments/synthesis. Neither route calls stage one,
  acquisition, browser or media upload.
- Optional first-entry interval reports use frozen [from,to) membership across
  runs, independent of publication/last observation. Per-request override never
  silently saves a new shared default.

## UI and History

Keep two visible stages and independent progress/errors. Automatic reports need
no generation dialog. Paginated sections include frozen citation projections;
XHS uses a valid stored origin tuple, other links use validated frozen URLs.
Old report links remain readable. UI GET/polling/route entry never submits work.

## Operational Boundaries

Review request counts and usage for large tasks; no unlimited context claim.
Keep automatic activation disabled until full A+B+C acceptance. Cancel/restart
preserve saved evidence and require explicit retry of interrupted paid work.
Rollback disables new admission and leaves additive snapshots/history intact.
