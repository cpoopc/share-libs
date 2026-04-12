# share-libs

Shared source repository for reusable cp-tools libraries, package-level runtimes, and canonical shared skills.

## Current migration scope

- `tools/python/libs/common`
- `tools/python/libs/confluence`
- `tools/python/libs/grafana`
- `tools/python/libs/jira`
- `tools/python/libs/kibana`
- `tools/python/libs/translation`
- `tools/web/libs/timeline`
- `packages/iva-logtracer`
- `packages/confluence-sync`
- `packages/grafana-report-fetching`
- `packages/jira-ticket-sync`
- `agents/skills/confluence`
- `agents/skills/grafana-report-fetching`
- `agents/skills/iva-jira-ticket-sync`
- `agents/skills/iva-logtracer`
- `agents/skills/jira-ticket-sync`
- `agents/skills/kafka`
- `agents/skills/kibana`

`tools/python/libs/kibana` owns the installed `kibana-query` CLI for generic log search and export.
`packages/confluence-sync` owns the installed `confluence-sync` CLI for Confluence search, extract, upload, and translation.
`packages/grafana-report-fetching` owns the installed `grafana-report-fetching` CLI for Grafana profile resolution, config-driven report fetches, and daily core metrics pulls.
`packages/iva-logtracer` owns the trace core, CLI, runners, templates, and output workflow.
`agents/skills/iva-logtracer` is the canonical skill source and should stay
portable: installed CLI only, no repo-relative commands.
`packages/jira-ticket-sync` owns the manifest-backed Jira sync runtime and CLI.
`cp-tools` may still own repo-local app shells and report runners, but canonical reusable libs and skills should move here first.

## Principles

- This repository is the source of truth for code intentionally shared outside `cp-tools`.
- `cp-tools` should consume published packages or tracked dependencies from this repository instead of keeping duplicate implementations.
- `cp-tools` may keep local app shells, but CLI workflows and skills should not depend on repo-local wrappers.
