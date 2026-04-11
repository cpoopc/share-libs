# IVA Defaults

These defaults apply on top of the shared installed `jira-ticket-sync` CLI.

## Root Variables

```bash
export IVA_JIRA_SYNC_ROOT="${XDG_CONFIG_HOME:-$HOME/.config}/jira-ticket-sync"
```

Override `IVA_JIRA_SYNC_ROOT` only when you want a different writable workspace:

```bash
export IVA_JIRA_SYNC_ROOT=/path/to/your/jira-ticket-sync-workspace
```

## Path Defaults

- Prefer `$IVA_JIRA_SYNC_ROOT/manifests/` for local ticket definitions.
- Prefer `$IVA_JIRA_SYNC_ROOT/profiles/IVAS.yaml` for IVAS work.
- Prefer `$IVA_JIRA_SYNC_ROOT/profiles/NOVA.yaml` for NOVA work.
- Prefer `$IVA_JIRA_SYNC_ROOT/project-config.yaml` for IVA query defaults such as board ID, sprint prefix, and team key.
- Keep `active.md` and daily logs as workflow records, not manifest sources.
- For recurring DevOps/SRE requests in Jira project `DO`, reuse `references/do-incident-template.md`.

## Example Commands

```bash
jira-ticket-sync status "$IVA_JIRA_SYNC_ROOT/manifests"
jira-ticket-sync push "$IVA_JIRA_SYNC_ROOT/manifests" --dry-run
jira-ticket-sync pull "$IVA_JIRA_SYNC_ROOT/manifests" --dry-run
jira-ticket-sync sprints --project IVAS --real --jira-project-config "$IVA_JIRA_SYNC_ROOT/project-config.yaml"
jira-ticket-sync epics --project IVAS --active-only --real --jira-project-config "$IVA_JIRA_SYNC_ROOT/project-config.yaml"
jira-ticket-sync import IVAS-6699 --real --profile "$IVA_JIRA_SYNC_ROOT/profiles/IVAS.yaml" --field-classification-root "$IVA_JIRA_SYNC_ROOT/state/field-classification"
```
