# Manifest Schema

## Profile

```yaml
profile:
  id: IVAS
  project: IVAS
  defaults:
    priority: Medium
  managed_fields:
    - summary
    - description
    - priority
    - labels
    - assignee
    - epic_key
    - sprint_id
    - fields.team
  field_aliases:
    team: customfield_10012
```

## Manifest

```yaml
manifest:
  id: sprint-2026-sp02-observability
  kind: sprint
  profile: IVAS

defaults:
  sprint_id: 36780
  epic_key: IVAS-6784
  priority: Medium
  labels:
    - observability

tickets:
  - local_id: nova-unstable-alert-gap
    jira_key: null
    issue_type: Task
    summary: Add missed alert for NOVA unstable
    description: Create alert coverage for the current NOVA unstable gap.
    fields:
      team: NOVA
```

