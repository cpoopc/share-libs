# share-libs

Shared source repository for reusable cp-tools libraries, package-level runtimes, and canonical shared skills.

## Install from local source

Recommended installer from a local checkout:

```bash
git clone git@github.com:cpoopc/share-libs.git ~/cp-share-libs
cd ~/cp-share-libs
bash ./install-share-libs.sh
```

Default behavior:

- local checkout path defaults to `~/cp-share-libs`
- if the target directory already contains the correct `share-libs` clone, the installer skips `git pull`
- the installer runs `bootstrap-all.sh --symlink-skills`
- shared CLIs install in editable mode, so local source changes take effect immediately
- skills install as symlinks under `~/.agents/skills`, so `SKILL.md` and reference edits take effect immediately

If you already have a `share-libs` clone and want to reuse it, just run the installer inside that checkout:

```bash
cd /path/to/share-libs
bash ./install-share-libs.sh
```

Low-level repo-root bootstrap entrypoints are still available when you want finer control:

```bash
# Install all discovered skills from this checkout
bash ./bootstrap-skills.sh

# Install the main shared CLIs, run their init flows, then install all skills
bash ./bootstrap-all.sh
```

Current `bootstrap-all.sh` covers the shared CLIs that already have install entrypoints in this repo:

- `packages/confluence-sync/install.sh`
- `packages/grafana-report-fetching/install.sh`
- `packages/iva-logtracer/install.sh`
- `packages/jira-ticket-sync/install.sh`
- `tools/python/libs/kibana/install.sh`

Current `bootstrap-skills.sh` installs every skill directory under `agents/skills/` that contains a `SKILL.md`.

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
