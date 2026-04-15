# IVA Defaults

These defaults apply on top of the shared installed `jira-ticket-sync` CLI.

## ⚠️ CRITICAL: Always Use Full Paths for Profile and Config Flags

The `jira-ticket-sync` CLI does NOT resolve bare profile names like `IVAS` or `NOVA`. Passing `--profile IVAS` causes `FileNotFoundError: 'IVAS'` because the CLI treats `IVAS` as a literal file path.

**Always expand profile names and config paths to their full paths:**

```bash
# ❌ WRONG — bare profile name causes FileNotFoundError
--profile IVAS
--profile NOVA

# ✅ CORRECT — full path to the profile YAML file
--profile "$IVA_JIRA_SYNC_ROOT/profiles/IVAS.yaml"
--profile "$IVA_JIRA_SYNC_ROOT/profiles/NOVA.yaml"
--profile "$IVA_JIRA_SYNC_ROOT/profiles/DO.yaml"
```

The same applies to `--jira-project-config`, `--profile-root`, `--field-classification-root`, and all other path-bearing flags. Always use the expanded variable form.

## Root Variables

```bash
export IVA_JIRA_SYNC_ROOT="${XDG_CONFIG_HOME:-$HOME/.config}/jira-ticket-sync"
```

Override `IVA_JIRA_SYNC_ROOT` only when you want a different writable workspace:

```bash
export IVA_JIRA_SYNC_ROOT=/path/to/your/jira-ticket-sync-workspace
```

## Path Defaults

- Profile root: `$IVA_JIRA_SYNC_ROOT/profiles/` — but always pass `--profile "$IVA_JIRA_SYNC_ROOT/profiles/<NAME>.yaml"`, never a bare name.
- Manifest root: `$IVA_JIRA_SYNC_ROOT/manifests/`
- Template root: `$IVA_JIRA_SYNC_ROOT/templates/imported/`
- State file: `$IVA_JIRA_SYNC_ROOT/state/sync-state.json`
- Field classification root: `$IVA_JIRA_SYNC_ROOT/state/field-classification/`
- Project config: `$IVA_JIRA_SYNC_ROOT/project-config.yaml`
- Keep `active.md` and daily logs as workflow records, not manifest sources.
- For recurring DevOps/SRE requests in Jira project `DO`, reuse `references/do-incident-template.md`.

## Example Commands

```bash
# Always expand profile names to full paths
jira-ticket-sync show INIT-25953 --real --profile "$IVA_JIRA_SYNC_ROOT/profiles/IVAS.yaml"

jira-ticket-sync status "$IVA_JIRA_SYNC_ROOT/manifests"
jira-ticket-sync push "$IVA_JIRA_SYNC_ROOT/manifests" --dry-run
jira-ticket-sync pull "$IVA_JIRA_SYNC_ROOT/manifests" --dry-run
jira-ticket-sync sprints --project IVAS --real --jira-project-config "$IVA_JIRA_SYNC_ROOT/project-config.yaml"
jira-ticket-sync epics --project IVAS --active-only --real --jira-project-config "$IVA_JIRA_SYNC_ROOT/project-config.yaml"
jira-ticket-sync import IVAS-6699 --real --profile "$IVA_JIRA_SYNC_ROOT/profiles/IVAS.yaml" --field-classification-root "$IVA_JIRA_SYNC_ROOT/state/field-classification"
```
