# Design — Audit and Push Remaining Changes

## Change Groups

### 1. Repository policy

`AGENTS.md` adds a project-wide local-first runtime rule. It lives outside the managed Trellis
block and is committed alone so operational policy can be reviewed or reverted independently.
The matching local-first paragraph in the initial-analysis spec belongs with this policy commit.

### 2. Trellis metadata

`.trellis/.template-hashes.json` records a real Trellis 0.6.16 template-render event and is
deliberately excluded from automatic Trellis staging. Commit only this file in a narrow metadata
commit; do not attempt to make the recorded upstream template hash equal a later personal overlay.

### 3. Toutiao historical-source compatibility

The functional change spans two Git repositories:

- MediaCrawler validates worker commands/results and owns browser navigation.
- The parent backend validates stored source identity and freezes analysis input.

The accepted legacy form is exact and matching-ID only. The canonical adversarial cases live in
MediaCrawler's versioned `enrichment_contract_v1.json`; both repositories consume that fixture.
The adapter test separately proves HTTP-to-HTTPS navigation while preserving the original source
URL in returned evidence.

## Publication Order

1. Complete and validate MediaCrawler coverage.
2. Commit and push MediaCrawler `main`.
3. Verify the pushed SHA through `git ls-remote`.
4. Validate the parent backend.
5. Commit parent policy and metadata separately.
6. Commit backend code/tests/spec URL-contract hunks with the updated MediaCrawler gitlink.
7. Prove recursive submodule reproducibility from a fresh temporary clone.
8. Push parent `main` and verify it matches `origin/main`.

This order prevents the parent from pointing at an unavailable child commit and prevents a parent
backend that admits sources an older worker would reject.

## Safety Boundaries

- Use exact explicit paths for staging in both repositories.
- Do not rewrite runtime SQLite data or historical URLs.
- Do not start or interact with browser/platform/model services.
- Do not force-push, rebase, reset, or discard unrelated work.
- Use a temporary directory for recursive-clone validation and remove it only through its own
  scoped temporary lifecycle.
