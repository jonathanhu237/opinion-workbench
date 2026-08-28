# 监控规则与真实采集链路验收

## Goal

Show how the current application performs on real platform searches: whether adding an issue
keyword improves relevance, whether repeated results are deduplicated, and whether the saved AI
provider accepts the implemented text connection test. Report evidence, not unit-test coverage as
a substitute for a live result.

## Confirmed Background

- The committed application supports five serial search targets and object/issue composition.
  The platform receives a space-joined query, not guaranteed Boolean AND semantics.
- The existing product database is version 8 and has one enabled five-object rule. All previous
  searches and batches are terminal. Its first object is the intended locality; integrity is OK.
- AI settings have a saved key reference and revision 1. Key-file readability and current model
  access are not proven by that metadata. Only a text connection-test endpoint is implemented;
  media enrichment, per-result AI analysis and final summaries remain separate planned tasks.
- Local app ports are not listening; Chrome's debugging port is listening, which does not prove
  authorization or platform login. Centaurus is reachable. See `research/current-boundary.md`.

## Requirements

- **R1 — Preserve existing state.** Back up the product database before starting the new app and
  applying its existing v9 migration. Preserve the original rule, historical IDs/observations and
  AI configuration. Never read, print, replace or synchronize credentials or browser profiles.
- **R2 — Bounded real comparison.** Use two clearly labelled acceptance rules: the existing primary
  locality by itself, and the same locality combined with the issue keyword `投诉`. Attempt one
  baseline and one combined-query search per supported platform, at most five retained results per
  query. Do not broaden topics, use user profiling or post/interact with platform content.
- **R3 — Real deduplication.** Repeat the same successful combined search once per eligible
  platform. Verify overlapping stable identities are reported as repeated, not inserted as new
  global contents. Different search results do not prove deduplication; report inconclusive samples.
- **R4 — Observable quality.** Inspect available title/snippet evidence and a small number of
  representative public originals. Distinguish locality-related issues, unrelated namesakes,
  advertising, neutral material and insufficient evidence. Do not infer spoken video content from
  a title or present a small sample as a measured recall/precision benchmark.
- **R5 — Saved AI configuration.** Send exactly one explicit text connection test using the saved
  revision and service-owned credential. The fixed synthetic prompt is the only provider input;
  no collected text, images or video are uploaded. Report failure without speculative retries.
- **R6 — Runtime ownership.** Approved scoped exception to the Centaurus runtime convention:
  run the lightweight backend and existing browser worker on the user's Mac so the browser and
  credentials stay local. Serve the frontend on Centaurus via loopback-only SSH forwarding;
  keep normal dependency/build checks there. The user approved this exception with the final plan.
- **R7 — Honest stopping and delivery.** Stop the relevant live flow for authorization, login,
  challenge or rate-limit blockers. Do not bypass or solve challenges. Preserve unrelated tabs.
  Keep acceptance results in the app, disable only the task-created rules after use, and provide
  actual outcome/count/link evidence plus explicit unimplemented/untested capability boundaries.

## Acceptance Criteria

- [x] R1: Backup and migration checks preserve the original rule, historical row identities/counts
  and non-secret AI revision; database integrity and foreign keys remain valid.
- [x] R2/R4: For each attempted platform, report baseline and combined-query outcomes, counts and
  observed relevance, with safe representative links or a concrete reason no sample was available.
  All five baseline searches passed; Toutiao's combined search failed and is explicitly recorded.
- [x] R3: Repeated successful searches preserve one global row per stable platform identity and
  show truthful new/repeated counts; inconclusive or blocked comparisons are explicitly labelled.
  Weibo/Douyin/Xiaohongshu: 15 proven overlaps. Kuaishou: inconclusive, zero overlap. Toutiao: not repeated.
- [x] R5: The actual saved-provider text test has a recorded status and elapsed time, with no key,
  raw provider output or collected content in evidence.
- [x] R6/R7: Runtime placement has approval; task-created data/tabs are identified, user-owned
  state is preserved, and the final application results are made accessible to the user.
- [x] R7: Report clearly separates live successes, live failures/manual blockers, and unimplemented
  media/analysis/summary work. No unsupported claim of complete end-to-end AI analysis is made.

These checkmarks mean the evidence/reporting requirements were fulfilled, not that every platform
or future AI capability passed. See `verification.md` for failures and inconclusive results.

## Out of Scope

Product or submodule code changes; implementing AI summaries or media collection; model/credential
changes; captcha automation; scraping comments/profiles; broad/unbounded retries; scheduled runs;
deleting history; changing original rules; commit/push or archiving other tasks.

## Approval Status

Task creation approved on 2026-08-27. Planning artifacts and read-only preflight are complete.
The user subsequently approved the final planning summary, including bounded searches, one text
model call, the existing migration and the scoped local-backend exception. Any discovered product
defect will be reported without an unapproved fix.

## Approved Rule Cleanup Follow-up — 2026-08-27

The user requested keeping one rule group and continuing. Keep original rule 1,
`龙田街道及四个社区`, unchanged; remove only task-created acceptance rules 3 and 4 through
the existing product API after a fresh private local backup. This supersedes retaining those
two rules disabled, not the requirement to preserve every run, batch and collected content.
Do not restrict the product to supporting only one rule or add issue keywords to the original.
No additional platform search, model invocation, product fix, commit or push is included.

- [x] Re-resolve all three rules and confirm no active runs/batches before cleanup.
- [x] Back up and validate the current local database before deleting exact rules 3 and 4.
- [x] Confirm only rule 1 remains, with every field and ordered term unchanged.
- [x] Compare all search-history rows against the backup, allowing only test-rule foreign keys
  to become null; verify database integrity and foreign keys.

See `research/rule-cleanup-verification.md` for evidence and the bounded next-step source audit.

## Authorized Real-Media Follow-up — 2026-08-28

The user explicitly approved trying a small sample of already collected videos to
measure model understanding and actual token usage. The controlling follow-up
scope is `research/media-cost-probe-plan.md`: at most three real media calls from
at most five inspected originals, using only the saved service-owned credentials.
This supersedes R5's historical synthetic-text-only limit for this experiment;
production media/summary implementation and bulk processing remain out of scope.
