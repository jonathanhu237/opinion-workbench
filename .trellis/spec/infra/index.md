# Infrastructure Specifications

Repository-level dependency and deployment conventions live in this layer.

## Pre-Development Checklist

Before adding or updating a Git submodule:

1. Read [Submodule Guidelines](./submodule-guidelines.md).
2. Confirm the remote revision is reachable before changing the parent gitlink.
3. Preserve unrelated working-tree changes in both the parent and submodule.

## Quality Check

- Validate `.gitmodules` syntax and the expected public URL.
- Confirm the parent index records mode `160000` for every submodule path.
- Run `git submodule status --recursive`.
- Prove reproducibility with a fresh temporary clone and recursive initialization.
- Confirm the submodule working tree is clean before committing the parent pointer.
