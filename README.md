# share-libs

Shared source repository for reusable cp-tools libraries and package-level runtimes.

## Initial migration scope

- `tools/python/libs/common`
- `tools/python/libs/kibana`
- `tools/web/libs/timeline`
- `packages/iva-logtracer`

`packages/iva-logtracer` owns the trace core, CLI, runners, templates, and output workflow.
`cp-tools` owns the local `apps/iva_logtracer` web application shell and runtime state.

## Principles

- This repository is the source of truth for code intentionally shared outside `cp-tools`.
- `cp-tools` should consume published packages or tracked dependencies from this repository instead of keeping duplicate implementations.
- Repo-local wrappers may exist in `cp-tools`, but they should stay thin and avoid duplicating core workflow logic.
