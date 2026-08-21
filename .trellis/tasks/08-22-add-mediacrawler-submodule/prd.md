# Add MediaCrawler fork as submodule

## Goal

Add the user's MediaCrawler fork to the repository as a pinned Git submodule so
future platform-specific crawler development can happen in the fork while this
project records an explicit, reproducible dependency revision.

## Background

- The main repository currently has no `.gitmodules` file and no `third_party/`
  directory.
- The selected fork is `https://github.com/jonathanhu237/MediaCrawler`.
- The fork's default branch is `main`; its current HEAD is
  `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`.
- MediaCrawler remains a separately versioned codebase. The parent repository
  should contain a Git link, not a copied source tree.

## Requirements

- Add the fork at the canonical path `third_party/MediaCrawler`.
- Configure the submodule with the public HTTPS URL so fresh clones and CI can
  initialize it without an SSH credential solely for this dependency.
- Pin the parent repository to an exact MediaCrawler commit; do not configure
  deployment to follow a floating branch automatically.
- Preserve MediaCrawler's own repository history, license, and working tree as
  the responsibility of the submodule repository.
- Keep the change limited to submodule integration and Trellis task artifacts.

## Acceptance Criteria

- [x] `.gitmodules` declares `third_party/MediaCrawler` with URL
      `https://github.com/jonathanhu237/MediaCrawler.git`.
- [x] `third_party/MediaCrawler` is recorded by the parent repository as a Git
      submodule entry pinned to an existing commit in the fork.
- [x] `git submodule status` reports the configured submodule without an error.
- [x] A fresh temporary clone followed by
      `git submodule update --init --recursive` checks out the same pinned
      MediaCrawler revision successfully.
- [x] No MediaCrawler source files are copied into the parent repository as
      ordinary tracked files.
- [x] No frontend, backend, crawler adapter, or runtime configuration is added
      as part of this task.

## Out of Scope

- Implementing the Toutiao collector.
- Modifying MediaCrawler source code or creating custom branches in the fork.
- Initializing frontend or backend applications.
- Adding deployment, scheduler, database, AI analysis, or notification code.
- Making licensing or production-usage determinations for MediaCrawler.

## Technical Notes

- The parent repository records a commit object for the submodule even though
  development in the fork may later occur on a custom branch.
- The current candidate revision is
  `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`; implementation must verify that
  the revision is still reachable from the fork before adding it.
- This is a lightweight repository-structure task, so a PRD is sufficient;
  separate `design.md` and `implement.md` artifacts are not required.
