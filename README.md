# share-libs

Shared source repository for reusable cp-tools libraries, runtimes, and portable skills.

## Initial migration scope

- `tools/python/libs/common`
- `tools/python/libs/kibana`
- `tools/web/libs/timeline`
- `apps/iva_logtracer`
- `agents/skills/iva-logtracer`

## Principles

- This repository is the source of truth for code intentionally shared outside `cp-tools`.
- `cp-tools` should consume published packages or tracked dependencies from this repository instead of keeping duplicate implementations.
- Repo-local wrappers may exist in `cp-tools`, but they should stay thin and avoid duplicating core workflow logic.
