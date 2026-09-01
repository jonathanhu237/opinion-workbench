# Research: Repository metadata and MediaCrawler remainder

- Query: Inspect `AGENTS.md`, `.trellis/.template-hashes.json`, and the dirty
  `third_party/MediaCrawler` submodule; determine provenance, commit suitability,
  validation, and safe push order.
- Scope: internal / external
- Date: 2026-09-01

## Findings

### Files found

- `AGENTS.md:1-18` — adds one repository-wide local-first runtime policy.
- `.trellis/.template-hashes.json:50-51` — updates only the recorded hashes for
  the Codex implement/check agent templates.
- `.trellis/scripts/common/safe_commit.py:49-80` — deliberately excludes the
  template-hash file from *automatic* Trellis staging; this is an accidental
  staging guard, not a Git ignore rule.
- `third_party/MediaCrawler/tools/enrichment_worker_protocol.py:120-143` —
  narrowly admits the observed Toutiao legacy URL ending in exactly
  `/?channel=` while retaining platform and content-ID equality checks.
- `third_party/MediaCrawler/tests/test_product_media_protocol.py:86-138` — adds
  the matching positive and adversarial protocol matrix.
- `.trellis/spec/infra/submodule-guidelines.md` — requires a clean submodule,
  reachable pushed child commit, mode `160000`, recursive status, and fresh
  recursive-clone proof before the parent gitlink is committed.

### `AGENTS.md`

The diff is coherent and repository-specific: the application depends on the
same local browser/CDP session as the collection worker, so local execution is a
real operating constraint rather than a personal preference. The block is
outside the managed `TRELLIS:START` section (`AGENTS.md:20`), so a future
`trellis update` should preserve it. The later backend spec edit explicitly
refers to this root local-first policy, confirming that the change belongs to
the same body of project decisions.

Recommendation: commit it in the parent repository as its own documentation /
repository-policy commit (for example, `docs: codify local-first runtime`). Do
this before the backend/spec commit that references the policy.

### `.trellis/.template-hashes.json`

The change predates the current work and is generated Trellis metadata, not a
product behavior change. The exact provenance can be reconstructed:

- The project is on Trellis `0.6.16`.
- Commit `f684879` already committed the 0.6.16 runtime/template upgrade.
- The remaining file timestamp is 2026-08-29 05:14 +0800, immediately before
  commit `b985e46` changed the two Codex agent model presets.
- Hash `7522ad...` is exactly the current official check template rendered with
  the then-preserved `gpt-5.6-sol` / `medium` settings.
- Hash `64e4b3...` is exactly the current official implement template rendered
  with `gpt-5.6-luna` / `max`.
- The project check agent now hashes to `cd5077...` because the local personal
  Trellis wrapper subsequently applied `gpt-5.6-luna` / `max`. This divergence
  is expected: the manifest records what Trellis last rendered, while the
  wrapper's project overlay is a local customization.

The generated-files documentation says not to hand-edit this file, and
`safe_commit.py:49-80` prevents broad automatic commits of it. However the file
is tracked, `f684879` previously committed it during a deliberate Trellis
upgrade, and this two-line diff records a real template-render event. It is safe
to commit deliberately in a narrow metadata-only commit such as
`chore(trellis): refresh template hashes`; do not combine it with product code
or rely on Trellis auto-archive/session staging to pick it up. The check-agent
hash need not equal the overlaid working file.

### `third_party/MediaCrawler`

The parent gitlink is unchanged at
`546b0d78fe51cfd7c86439baf6129d441a050414`, mode `160000`. The submodule is not
at a moved local commit: its `main`, local `origin/main`, and the live GitHub
`refs/heads/main` all resolve to that SHA, with ahead/behind `0/0`.

The lowercase `m` is solely an internally dirty submodule. It contains exactly
two tracked modifications and no untracked files:

1. `tools/enrichment_worker_protocol.py` changes the strict Toutiao HTTP legacy
   regex from the no-query forms to the same forms plus exactly
   `/?channel=`. Platform must still be `toutiao`, the numeric path ID must equal
   `content_id`, and the full regex excludes other hosts, ports, credentials,
   fragments, nonempty/duplicate/extra queries, and path variants.
2. `tests/test_product_media_protocol.py` adds 19 cases and checks both command
   parsing and enriched-content validation. The change is internally coherent
   and mirrors the parent backend validator/tests/spec rather than being an
   unrelated fork edit.

The child changes should be committed and pushed in the MediaCrawler repository
first. Only after GitHub exposes the new child SHA should the parent repository
stage the new `third_party/MediaCrawler` gitlink. This follows the submodule
contract and prevents a parent commit that fresh clones cannot initialize.

Recommended validation before the child commit:

```bash
cd third_party/MediaCrawler
python -m pytest tests/test_product_media_protocol.py -q
python -m pytest -q
git diff --check
git status --short
```

Suggested child commit: `fix(toutiao): accept legacy empty channel URL`. Push
that child commit to `origin/main`, verify `git ls-remote --heads origin main`
returns the new SHA, then return to the parent. In the parent, run the paired
backend tests/gates, stage the backend validator, its two tests, the backend
spec, and the updated gitlink together, and commit them as one compatibility
change. Finally validate `git submodule status --recursive`, mode `160000`, a
fresh temporary recursive clone, and `git diff --check` before pushing parent
`main`.

### Safe parent sequencing

1. Commit `AGENTS.md` alone.
2. Deliberately commit `.trellis/.template-hashes.json` alone (or explicitly
   leave it local, but do not accidentally sweep it into a product commit).
3. Run focused and full MediaCrawler tests; commit and push the two child files.
4. Confirm the new child SHA is reachable from the configured HTTPS remote.
5. Run the parent backend focused/full gates; commit the backend validator,
   paired tests/spec, and the new MediaCrawler gitlink together.
6. Prove recursive clone reproducibility and push parent `main`.

Current read-only checks: both parent metadata diffs and the child diff pass
`git diff --check`; `.gitmodules` uses
`https://github.com/jonathanhu237/MediaCrawler.git`; the existing child SHA is
present on live `origin/main`.

## External references

- MediaCrawler configured remote: `https://github.com/jonathanhu237/MediaCrawler.git`.
  Live `refs/heads/main` was checked on 2026-09-01 and matched the pinned SHA.
- Installed Trellis CLI/version used for provenance: `0.6.16` and its local
  generated-file documentation.

## Related specs

- `.trellis/spec/infra/index.md`
- `.trellis/spec/infra/submodule-guidelines.md`
- `.trellis/spec/backend/initial-analysis-guidelines.md` (currently modified;
  defines the parent/worker validator parity requirement)
- Root `AGENTS.md` local-first runtime policy

## Caveats / Not Found

- No test suite was executed by this research-only agent; the commands above are
  the required implementation/check phase gates.
- The future MediaCrawler commit does not exist yet, so only the currently pinned
  SHA could be proven reachable. Reachability must be repeated after the child
  push and before committing the parent pointer.
- File timestamps and prior task notes establish that these edits predate the
  current audit, but Git cannot identify which interactive session authored an
  uncommitted line.
