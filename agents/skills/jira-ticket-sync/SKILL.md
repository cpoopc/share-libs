---
name: jira-ticket-sync
description: Use for manifest-backed Jira workflows driven by local manifests, reusable profiles, and state directories, including import, show, status, dry-run, push, pull, sprint lookup, epic lookup, and field classification. Do not use for ad-hoc JQL search, sprint reports, or direct issue updates; use `jira` for those direct Jira operations.
---

# jira-ticket-sync

Use this skill when the user wants a manifest-backed Jira workflow instead of editing tickets manually in the Jira UI.

Install once on a new machine with:

```bash
bash packages/jira-ticket-sync/install.sh
```

Manual fallback:

```bash
uv tool install git+ssh://git@github.com/cpoopc/share-libs.git#subdirectory=packages/jira-ticket-sync
npx skills add /path/to/share-libs --skill jira-ticket-sync -g -y
jira-ticket-sync init
jira-ticket-sync doctor
```

## Scope Boundaries

- Use this skill for local manifest/profile/state workflows that synchronize Jira tickets in batches or from declarative files.
- Do not use this skill for ad-hoc Jira issue search, sprint reporting, or direct issue updates. Use `jira` for those direct Jira tasks.
- Keep workspace-specific defaults out of this core skill. Add them in thin wrapper skills such as `iva-jira-ticket-sync`.

## References

- Read `references/commands.md` for installed-command usage examples.
- Read `references/common-scenarios.md` for ready-to-run Epic, sprint item, import, and update flows.
- Read `references/schema.md` when editing or reviewing manifests and profiles.
- Read `references/ai-field-classification.md` only after import has reduced fields to a review-sized candidate set.
- Read `references/do-incident-template.md` when the task is a DO incident or SRE-style ticket.

## Workflow

1. Prefer the installed CLI over repo-relative scripts.
2. Run `jira-ticket-sync init` on a fresh machine before the first real Jira call.
3. Use `jira-ticket-sync doctor` if auth or workspace state is unclear.
4. Identify the manifest root or the specific manifest file.
5. Choose or create a profile for the target Jira project.
6. If fields are unclear, import one or more existing Jira tickets first.
7. Review the import output for `common_fields`, `issue_type_fields`, `candidate_fields`, and `ignored_fields`.
8. When `candidate_fields` are still ambiguous, run an AI field-classification pass before editing manifests or profiles.
9. Update or generate manifest content locally.
10. Run `status`.
11. Run `push --dry-run` or `pull --dry-run`.
12. Execute `push --real` or `pull --real` only after the preview looks correct.

## Rules

- Keep manifests human-readable. Do not put raw `customfield_*` IDs in manifests.
- Resolve custom fields through profile aliases.
- Do not treat Jira workflow status as a normal synchronized field.
- Prefer manifest-first execution even when the user starts from conversation input.
- Keep workspace-specific defaults out of the core command. Use explicit CLI paths or a wrapper skill for local conventions.
- When users provide ticket requests in short Chinese text, write Jira `summary` and `description` in polished English while preserving the original intent and scope.
- Treat optional custom fields as best effort during real push. Some Jira screens reject fields like `team_keys` for specific issue types even when the field alias exists in the profile.

## Validation

- Confirm `jira-ticket-sync doctor` is clean enough for the requested operation when auth or config is in doubt.
- Confirm real commands use a configured `.env` file or exported environment variables.
- Confirm `push --dry-run` or `pull --dry-run` before destructive real sync when the user did not explicitly ask to skip preview.
- Confirm generated manifests keep aliases, not raw Jira field IDs.
