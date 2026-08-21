# Git Submodule Guidelines

## Scenario: Versioned third-party source dependency

### 1. Scope / Trigger

Use this contract when third-party source must retain its own Git history while
the parent project pins a reproducible revision. Third-party repositories belong
under `third_party/<RepositoryName>` and must not be copied into the parent as
ordinary tracked source files.

### 2. Signatures

Add a public dependency:

```bash
git submodule add https://github.com/<owner>/<repository>.git third_party/<RepositoryName>
```

Initialize the revision recorded by the parent:

```bash
git submodule update --init --recursive
```

Validate the configured graph:

```bash
git submodule status --recursive
git ls-files --stage third_party/<RepositoryName>
```

### 3. Contracts

- `.gitmodules` contains exactly one matching `path` and `url` entry.
- Public dependencies use an HTTPS URL so clean clones do not require an SSH
  credential solely to read the dependency.
- The parent index records the submodule path with Git mode `160000` and an
  exact commit SHA.
- The pinned SHA is reachable from the configured remote.
- The submodule working tree is clean when the parent pointer is committed.
- Changes to third-party source are committed and pushed in the third-party
  repository before the parent updates its gitlink.

No environment variables are required for public submodules. Private
submodules must document their credential mechanism before adoption.

### 4. Validation & Error Matrix

| Condition | Required result |
| --- | --- |
| `.gitmodules` path or URL is missing | Reject the change |
| Parent index mode is not `160000` | Reject; source was vendored incorrectly |
| Pinned SHA is absent from the remote | Reject; fresh clones are not reproducible |
| Submodule working tree is dirty | Commit/push or discard only the intended submodule changes before proceeding |
| Recursive initialization fails | Reject and correct URL, credentials, or revision |
| Public dependency requires SSH | Replace with HTTPS unless authenticated access is an explicit requirement |

### 5. Good / Base / Bad Cases

- **Good:** Public HTTPS URL, mode `160000`, reachable SHA, clean working tree,
  and a fresh clone checks out the exact revision.
- **Base:** The submodule is initialized locally and `git submodule status`
  matches the parent gitlink, but fresh-clone validation is still required.
- **Bad:** Third-party files appear individually in `git ls-files`, the remote
  cannot provide the recorded SHA, or the parent points at an unpushed local
  submodule commit.

### 6. Tests Required

1. Assert `.gitmodules` has the expected path and URL.
2. Assert `git ls-files --stage` reports mode `160000` and the expected SHA.
3. Assert `git submodule status --recursive` exits successfully.
4. Assert `git -C third_party/<RepositoryName> status --short` is empty.
5. Create a temporary parent commit, clone it into a new temporary directory,
   run recursive initialization, and assert the nested `HEAD` equals the
   parent's gitlink SHA.
6. Run `git diff --check` for staged and unstaged metadata changes.

### 7. Wrong vs Correct

#### Wrong

```text
third_party/MediaCrawler/main.py   # ordinary parent-repository file
url = git@github.com:owner/public-repository.git
gitlink = local commit that was never pushed
```

#### Correct

```text
.gitmodules URL = https://github.com/owner/repository.git
third_party/MediaCrawler mode = 160000
gitlink SHA = reachable commit in the configured remote
```
