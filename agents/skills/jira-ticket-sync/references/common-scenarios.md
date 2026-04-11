# Common Scenarios

Use this file when the task is already clear and you want the shortest path to a working Jira manifest flow.

## 1. Create an IVAS Epic in the next sprint

Use when the user gives a short request such as "创建一个 IVAS Epic, 放到下个 sprint".

Recommended flow:

1. Bootstrap a writable workspace.
2. Copy `.env.example` to `.env` and set `JIRA_USE_BEARER=true`.
3. List IVAS sprints to get the next sprint id.
4. Create an Epic manifest under `manifests/<year>/<quarter>/epic/`.
5. Run `status`.
6. Run `push --dry-run`.
7. Run `push --real`.

Example commands:

```bash
python3 scripts/bootstrap_workspace.py --target /tmp/jira-ticket-sync-workspace
cp /tmp/jira-ticket-sync-workspace/.env.example /tmp/jira-ticket-sync-workspace/.env
python3 scripts/jira-ticket-sync sprints --project IVAS --real
python3 scripts/jira-ticket-sync status /tmp/jira-ticket-sync-workspace/manifests/2026/q2/epic/my-initiative/my-epic.yaml
python3 scripts/jira-ticket-sync push /tmp/jira-ticket-sync-workspace/manifests/2026/q2/epic/my-initiative/my-epic.yaml --dry-run
python3 scripts/jira-ticket-sync push /tmp/jira-ticket-sync-workspace/manifests/2026/q2/epic/my-initiative/my-epic.yaml --real
```

Minimal manifest shape:

```yaml
manifest:
  id: my-epic
  kind: epic
  profile: IVAS

tickets:
  - local_id: my-epic
    jira_key: null
    issue_type: Epic
    summary: Replace with epic summary
    description: |
      Goal:

      Replace with polished English description.
    sprint_id: 36908
    fields:
      epic_name: Replace with epic summary
      target_start: 2026-03-23
      target_end: 2026-04-05
      public_summary: Optional short public summary
      team_keys: TEAM-32036
```

Notes:

- Prefer writing `summary` and `description` in polished English even if the source request is Chinese.
- Real `push` now assigns `sprint_id` through the Jira Agile sprint API.
- If Jira still rejects a field such as `team_keys`, treat that field as best effort and do not block ticket creation on it.

## 2. Create a Task or Story under an existing Epic

Use when the user already has an Epic key and wants a sprint backlog item.

Recommended flow:

1. Confirm the target Epic key.
2. Confirm or look up the sprint id.
3. Create a manifest under `manifests/<year>/<quarter>/sprint/sprint-<id>/`.
4. Use `epic_key` and `sprint_id` in the ticket body.
5. Preview with `push --dry-run`.
6. Execute with `push --real`.

Minimal manifest shape:

```yaml
manifest:
  id: my-sprint-item
  kind: sprint
  profile: IVAS

tickets:
  - local_id: my-sprint-item
    jira_key: null
    issue_type: Task
    summary: Replace with task summary
    description: Replace with task description.
    epic_key: IVAS-7008
    sprint_id: 36908
    fields:
      team_keys: TEAM-32036
```

Notes:

- Use `issue_type: Task` unless the user clearly needs `Bug`, `User Story`, or another mapped type.
- Keep the manifest readable. Do not inline `customfield_*` ids.

## 3. Check the next sprint before writing a manifest

Use when the user says "下个 sprint", "next sprint", or gives only a relative sprint request.

Command:

```bash
python3 scripts/jira-ticket-sync sprints --project IVAS --real
```

Interpretation guidance:

- Pick the next `future` sprint when the user says "next sprint".
- Use the absolute sprint id in the manifest, not just the sprint name.

## 4. Find active IVAS Epics before attaching work

Use when the user wants to place work under an existing Epic but does not know the key.

Command:

```bash
python3 scripts/jira-ticket-sync epics --project IVAS --active-only --real
```

Notes:

- Use `--profile` only when you need profile alias rendering elsewhere such as `show`.
- This helper is `--real` only.

## 5. Inspect a Jira ticket and map custom fields to aliases

Use when fields are unclear or you need to see how an existing Epic or Task is structured.

Command:

```bash
python3 scripts/jira-ticket-sync show IVAS-7008 --real --profile /tmp/jira-ticket-sync-workspace/profiles/IVAS.yaml
```

Notes:

- `show` is the fastest way to confirm whether a field such as `parent_link`, `team_keys`, or `public_summary` is actually present on a comparable ticket.
- Prefer this before inventing new manifest fields.

## 6. Start from an existing Jira ticket and import its field shape

Use when the issue type is unfamiliar or the project has many custom fields.

Commands:

```bash
python3 scripts/jira-ticket-sync import IVAS-6699 --real --profile /tmp/jira-ticket-sync-workspace/profiles/IVAS.yaml --field-classification-root /tmp/jira-ticket-sync-workspace/state/field-classification
```

Notes:

- Import first, then decide which candidate fields belong in the manifest or profile.
- Do not copy the raw Jira field dump directly into the manifest.

## 7. Update an existing manifest-backed ticket

Use when the manifest already has `jira_key` and the user wants to revise summary, description, labels, or dates.

Recommended flow:

1. Edit the manifest.
2. Run `status`.
3. Run `push --dry-run`.
4. Run `push --real`.

Notes:

- If the issue already exists, the backend will use `UPDATE`.
- If the manifest still includes `sprint_id`, real `push` will keep trying to place the issue into that sprint through the Agile sprint API.

## 8. Troubleshoot a slow or failing real push

Use when the flow appears correct but the real command still fails or requires manual cleanup.

Check in this order:

1. Is the workspace `.env` present and configured, with `JIRA_USE_BEARER=true` for RingCentral Jira?
2. Does the workspace `project-config.yaml` expose the project field mappings needed for Epic creation?
3. Did `push --dry-run` produce the expected `CREATE` or `UPDATE` action?
4. Did real `push` warn about `dropped_fields`?
5. Did the ticket get created but miss sprint placement or other follow-up fields?

Typical interpretations:

- `Epic Name is required` usually means `project-config.yaml` was not discovered or does not define `fields.epic_name`.
- `dropped_fields=...` usually means Jira rejected those fields on the current screen. Treat them as best effort unless the ticket truly depends on them.
- If the issue exists but is not in the sprint, verify `sprint_id` and rerun `push --real`.
