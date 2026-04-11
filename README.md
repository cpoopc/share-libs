# share-libs

Shared source repository for reusable cp-tools libraries and package-level runtimes.

## Initial migration scope

- `tools/python/libs/common`
- `tools/python/libs/kibana`
- `tools/web/libs/timeline`
- `packages/iva-logtracer`
- `agents/skills/iva-logtracer`

`packages/iva-logtracer` owns the trace core, CLI, runners, templates, and output workflow.
`agents/skills/iva-logtracer` is the canonical skill source and should stay
portable: installed CLI only, no repo-relative commands.
`cp-tools` owns the local `apps/iva_logtracer` web application shell and runtime state.

## Principles

- This repository is the source of truth for code intentionally shared outside `cp-tools`.
- `cp-tools` should consume published packages or tracked dependencies from this repository instead of keeping duplicate implementations.
- `cp-tools` may keep local app shells, but CLI workflows and skills should not depend on repo-local wrappers.
