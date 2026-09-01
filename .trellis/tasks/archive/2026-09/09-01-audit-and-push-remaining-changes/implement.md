# Implementation Plan — Audit and Push Remaining Changes

## 1. Audit

- [x] Record every parent and child dirty path and classify it into policy, Trellis metadata, or
  Toutiao compatibility.
- [x] Confirm child branch/remote reachability and parent gitlink mode before mutation.

## 2. Complete MediaCrawler Coverage

- [x] Add the empty-`channel` accepted/rejected cases to the shared enrichment fixture.
- [x] Remove or reduce duplicated per-repository matrices so the shared fixture is authoritative.
- [x] Add the exact new stored URL to the Toutiao HTTPS-navigation regression.
- [x] Run targeted protocol/navigation tests and the full MediaCrawler suite.

## 3. Publish MediaCrawler

- [x] Stage only the worker, shared fixture, and affected tests.
- [x] Commit with a Conventional Commit and push child `main`.
- [x] Verify the new SHA is reachable from `origin/main` and the child worktree is clean.

## 4. Validate and Commit Parent Changes

- [x] Run backend Ruff check/format, focused tests, and the full pytest suite.
- [x] Commit `AGENTS.md` plus the matching local-first spec paragraph separately.
- [x] Commit `.trellis/.template-hashes.json` separately.
- [x] Commit backend validator/tests, URL-contract spec hunks, and the updated MediaCrawler gitlink
  together.

## 5. Reproducibility and Push

- [x] Verify parent gitlink mode `160000`, recursive status, remote child SHA, and clean child tree.
- [x] Clone the parent into a temporary directory, initialize recursively, and prove the nested HEAD
  equals the parent gitlink.
- [x] Run parent `git diff --check`, task validation, and final status review.
- [x] Push parent `main` and verify it matches `origin/main`.

## 6. Closeout

- [x] Record exact commands/results/SHAs in `verification.md`.
- [x] Archive the Trellis task and record the session journal without capturing unrelated changes.
