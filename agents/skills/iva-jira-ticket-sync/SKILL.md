---
name: iva-jira-ticket-sync
description: IVA and NOVA wrapper around the shared `jira-ticket-sync` CLI that defaults to the local XDG Jira sync workspace and uses IVA-specific manifests, profiles, templates, and state.
---

# iva-jira-ticket-sync

Use this skill when the task is clearly IVA or NOVA ticket work and the user wants IVA defaults without passing every manifest, profile, and state path manually.

## Install

Install the CLI first:

```bash
uv tool install git+ssh://git@github.com/cpoopc/share-libs.git#subdirectory=packages/jira-ticket-sync
```

Install this wrapper skill:

```bash
npx skills add https://github.com/cpoopc/share-libs --skill iva-jira-ticket-sync -g -y
```

## Workspace Contract

By default this shared wrapper uses the same XDG config workspace as the installed CLI:

```bash
${XDG_CONFIG_HOME:-$HOME/.config}/jira-ticket-sync
```

If you want a different IVA-specific data root, override it explicitly:

```bash
export IVA_JIRA_SYNC_ROOT=/path/to/your/jira-ticket-sync-workspace
```

## Defaults

- Manifest root: `$IVA_JIRA_SYNC_ROOT/manifests/`
- Profile root: `$IVA_JIRA_SYNC_ROOT/profiles/`
- Template root: `$IVA_JIRA_SYNC_ROOT/templates/imported/`
- State file: `$IVA_JIRA_SYNC_ROOT/state/sync-state.json`
- Field classification root: `$IVA_JIRA_SYNC_ROOT/state/field-classification/`
- Project config: `$IVA_JIRA_SYNC_ROOT/project-config.yaml`

## Workflow

1. Prefer `${XDG_CONFIG_HOME:-$HOME/.config}/jira-ticket-sync` unless the user explicitly points to another `IVA_JIRA_SYNC_ROOT`.
2. Confirm `$IVA_JIRA_SYNC_ROOT` exists before running real sync commands.
3. Use the shared `jira-ticket-sync` CLI, but prefer IVA-local paths from this wrapper unless the user explicitly points elsewhere.
4. When the request is in short Chinese, write Jira `summary` and `description` in polished English while preserving the intent.
5. When import leaves ambiguous fields, keep IVA decisions in the IVA-local field-classification cache before promoting stable aliases into `profiles/IVAS.yaml`.

## References

- Read `references/iva-defaults.md` for IVA-rooted command examples.
- Read `references/do-incident-template.md` for recurring DO incident requests tied to IVA environments.

## Validation

- Confirm `$IVA_JIRA_SYNC_ROOT` exists before using IVA defaults.
- Confirm `jira-ticket-sync doctor` is clean enough when auth or workspace state is unclear.
- Confirm `push --dry-run` or `pull --dry-run` before real sync when the user did not explicitly ask to skip preview.
