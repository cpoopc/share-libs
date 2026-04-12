# jira-ticket-sync

Installable Jira manifest sync CLI for manifest-backed workflows.

## Install

Recommended bootstrap:

```bash
bash packages/jira-ticket-sync/install.sh
```

From a local checkout this installs the CLI in editable mode, so the installed command follows the current clone. Use `--release-cli` when you need to validate the packaged install path instead.

Manual fallback:

```bash
uv tool install --force --editable /path/to/share-libs/packages/jira-ticket-sync
uv tool install --force git+ssh://git@github.com/cpoopc/share-libs.git#subdirectory=packages/jira-ticket-sync
jira-ticket-sync init
jira-ticket-sync doctor
```

Optional IVA wrapper skill:

```bash
npx skills add https://github.com/cpoopc/share-libs --skill iva-jira-ticket-sync -g -y
```

The IVA wrapper defaults to the same XDG config workspace root:

- `~/.config/jira-ticket-sync/`
- override with `IVA_JIRA_SYNC_ROOT=/path/to/your/jira-ticket-sync-workspace`

## Core Commands

```bash
jira-ticket-sync init
jira-ticket-sync doctor
jira-ticket-sync status path/to/manifests
jira-ticket-sync push path/to/manifests --dry-run
jira-ticket-sync pull path/to/manifests --dry-run
jira-ticket-sync import IVAS-6699 --real --profile path/to/profiles/IVAS.yaml
jira-ticket-sync show IVAS-6699 --real --profile path/to/profiles/IVAS.yaml
jira-ticket-sync sprints --project IVAS --real
jira-ticket-sync epics --project IVAS --active-only --real
```

## Runtime Layout

By default the CLI uses XDG paths:

- config workspace: `~/.config/jira-ticket-sync/`
- cache/output root: `~/.cache/jira-ticket-sync/`

`jira-ticket-sync init` seeds the config workspace with:

- `.env.example`
- `project-config.yaml`
- `manifests/`
- `profiles/`
- `templates/imported/`
- `state/`

When the command is run inside a different manifest workspace, explicit paths still win.

## Development

```bash
cd packages/jira-ticket-sync
uv sync
pytest cptools_jira_ticket_sync/tests -q
```
