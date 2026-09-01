# 审查并推送遗留改动

## Goal

逐项审查当前未提交的后端、规范、仓库配置和 MediaCrawler 子模块改动，运行对应验证，按归属拆分提交并推送。

## Requirements

- Inspect every pre-existing dirty path and classify it by intent, repository, and commit boundary.
- Preserve the narrow historical Toutiao compatibility contract: accept only a matching numeric
  `http://www.toutiao.com/a<ID>/?channel=` source, keep the stored URL unchanged, and upgrade to
  HTTPS only at browser navigation.
- Keep the parent backend validator and MediaCrawler worker validator synchronized through the
  shared golden fixture and adapter-level navigation coverage.
- Validate MediaCrawler in its own environment and the backend with its complete Ruff and pytest
  gates. No live platform, browser, model, or runtime-database operation is authorized.
- Commit and push the MediaCrawler child repository before updating the parent gitlink; prove the
  child SHA is reachable from its configured remote.
- Commit repository policy (`AGENTS.md`) and generated Trellis template metadata separately from
  product code. Do not sweep unrelated files into a commit.
- After parent commits, prove mode `160000`, clean recursive submodule state, and fresh recursive
  clone reproducibility before pushing parent `main`.
- Record exact tests, commit SHAs, remote reachability, and any remaining caveats.

## Acceptance Criteria

- [ ] Every initial dirty path is accounted for, with no unexplained or accidentally staged file.
- [ ] The shared enrichment fixture covers the accepted empty-`channel` form and close rejected
  variants on both backend and worker boundaries.
- [ ] Toutiao adapter tests prove one HTTPS navigation, exact stored-source preservation, and no
  user-tab cleanup for the new form.
- [ ] MediaCrawler targeted and full tests pass; its commit is pushed and remotely reachable.
- [ ] Backend Ruff check, Ruff format check, targeted tests, and full pytest pass.
- [ ] Local-first policy, Trellis metadata, and the functional parent change are separate
  Conventional Commits.
- [ ] Parent gitlink points to the pushed child commit; recursive status and fresh-clone validation
  pass.
- [ ] Parent `main` is pushed and matches `origin/main`; no task-owned dirty files remain.
- [ ] No external platform, browser, model, or runtime-database work occurs during validation.

## Notes

- The dirty changes predate this audit; Git cannot identify their interactive author.
- Research found a coherent product fix plus two independent repository-maintenance changes.
- Push authorization covers both the MediaCrawler remote and the parent repository remote.
