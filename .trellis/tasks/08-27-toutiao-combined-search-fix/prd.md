# 头条组合搜索修复

## Goal

Diagnose and fix the Toutiao combined-query failure so a bounded public first-page search can
return recognized results or a truthful empty result, without weakening safety or data boundaries.

## Current follow-up

The user requested investigation and repair of the later run-47 failure on 2026-08-28. The
previous repair and delivery below are historical. Current scope, fresh validation limits and
ownership are in `research/run47-followup-plan.md`. Git delivery was deferred during implementation;
the user's subsequent `好的，请你 commit 并 push 吧。` now explicitly authorizes the scoped
two-repository delivery described in `research/run47-delivery.md`. A full-batch retry and archival
remain out of scope. Reuse this task without replacing its earlier evidence.

## Background and Approval

- Prior acceptance: baseline run 29 succeeded; combined run 34 (`龙田街道 投诉`) ended in
  `structure_changed`. The stored outcome does not establish the underlying cause.
- The client currently takes one DOM snapshot 1.5 seconds after navigation and requires one
  `.s-result-list`; several structure/normalization errors share the same public outcome.
- Current unmodified live reproduction (run 43) succeeded with two results. Mature visible DOM
  also yields two candidates using the exact existing script. The historical failure is not
  conclusively reproduced. The bounded repair targets the independently testable delayed-render
  false-negative gap, not a claimed proven selector change or definitive cause of run 34.
- The user explicitly requested this Trellis task and implementation, delegating the planning
  approval so work may proceed without another user response. Record that delegation honestly;
  do not impersonate a new user approval. Browser login/challenges remain manual.
- Original rule 1 is the only retained rule. Previous uncommitted UI changes belong to other work.
- After implementation and acceptance, the user explicitly requested `提交推送`. This authorizes
  committing/pushing this repair on both repositories' existing `main` branches: derivative first,
  then the reachable parent gitlink with its task/spec evidence. Unrelated dirty work and archival
  remain outside this delivery request.

## Requirements

- R1: Establish a specific reproducible cause using bounded DOM evidence and/or a failing fixture
  before choosing a fix. Do not assume a longer sleep solves the failure.
- R2: Fix only the demonstrated Toutiao search gap. Preserve official navigation, main-column
  scoping, stable URL identity, bounded cards, no private endpoint fallback and no navigation retry.
- R3: Keep results, explicit empty state, login/challenge/block and unknown structure distinct.
  Cancellation and user-tab ownership must remain intact.
- R3a: A valid pending result DOM must be allowed a bounded readiness window after the existing
  initial wait. Stop immediately on recognized outcomes or invalid/unsafe structure; expiration
  is still a structure failure, never an empty success. No reload or second search request.
- R4: Preserve the existing worker/API schema, SQLite history, content deduplication, formal rule,
  other platform behavior and unrelated source changes.
- R5: Allow one unmodified reproduction and one post-fix combined query through the existing product
  worker, cap retained results at five, then at most one repeat and one baseline regression if the
  platform succeeds. The separate owned diagnostic page is not a product acceptance run.
  A temporary task-labelled rule may be used only for this product test and must be deleted after
  terminal completion, leaving rule 1 unchanged. Preserve resulting history and take a fresh local
  backup first. The user previously explicitly approved this application's control of the same
  everyday Chrome session and asked the agent to accept its routine remote-debugging prompt.
  Reaccepting that same prompt after the owned backend reload is within that existing authority;
  it does not authorize new permissions, security-setting changes, platform login or CAPTCHA work.
  Stop on unexpected authorization/login/challenge/block rather than retrying automatically.
- R6: Edit only local code; synchronize source one-way and run tests on Centaurus. The already
  approved lightweight local backend/browser-worker exception is retained for live validation.
  Keep credentials, runtime databases, profiles and raw page data off Centaurus and out of evidence.

## Acceptance Criteria

- [x] Evidence distinguishes the reproduced delayed-render defect, current live success and
  unresolved historical cause, without relabelling run 34 or inventing a successful fix replay.
- [x] A regression fixture fails before the fix and passes afterward, with relevant near-miss and
  safety/lifecycle coverage.
- [x] The maintained MediaCrawler suite and affected backend regression suite pass on Centaurus.
- [x] Real combined search yields truthful results/empty state through the product worker; any
  incomplete live gate is clearly reported. A repeat verifies identity reuse when overlap exists.
- [x] Only formal rule 1 remains after tests; historical IDs/first-seen data, database integrity,
  foreign keys and unrelated browser tabs remain intact.
- [x] Independent review passes and changed contracts/lessons are recorded in the relevant spec.

## Out of Scope

Publication-time sorting is a separately requested follow-up, not part of this repair. No new
platform, full-text/media enrichment, AI request, schedule, broad pagination, challenge automation,
rule redesign, UI restyle or archival is included. Commit/push was deferred during implementation
and is now explicitly authorized as described above. Never advance the parent gitlink to an
uncommitted/unpushed derivative.
