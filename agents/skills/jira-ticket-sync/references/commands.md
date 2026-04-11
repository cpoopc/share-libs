# Commands

## First-Time Setup

```bash
jira-ticket-sync init
jira-ticket-sync doctor
```

## Status

```bash
jira-ticket-sync status path/to/manifests
```

## Show A Jira Ticket

```bash
jira-ticket-sync show IVAS-7008 --real --profile path/to/profiles/IVAS.yaml
```

## Push Preview

```bash
jira-ticket-sync push path/to/manifests --dry-run
```

## Pull Preview

```bash
jira-ticket-sync pull path/to/manifests --dry-run
```

## Real Push

```bash
jira-ticket-sync push path/to/manifests --real
```

## Real Pull

```bash
jira-ticket-sync pull path/to/manifests --real
```

## Import Template Preview

```bash
jira-ticket-sync import IVAS-6699 IVAS-6698 --dry-run
```

## Import With Field Classification Cache

```bash
jira-ticket-sync import IVAS-6699 --real --profile path/to/profiles/IVAS.yaml --field-classification-root path/to/state/field-classification
```

## List Sprints

```bash
jira-ticket-sync sprints --project IVAS --real
```

## List Active Epics

```bash
jira-ticket-sync epics --project IVAS --active-only --real
```

## Inspect Workspace Defaults

```bash
jira-ticket-sync resolve-paths --format text
```

## Bootstrap A Writable Workspace Elsewhere

```bash
jira-ticket-sync bootstrap-workspace --target /tmp/jira-ticket-sync-workspace
```
