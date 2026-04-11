from __future__ import annotations

from pathlib import Path
from typing import Any

from .field_classification_store import load_field_classifications
from .import_engine import build_import_template
from .jira_backend import CpToolsJiraBackend, JiraBackend, build_operation_plan, extract_field_aliases
from .manifest_loader import load_manifest, resolve_ticket, update_ticket_in_manifest
from .models import (
    EpicRequest,
    EpicResult,
    ImportRequest,
    ImportResult,
    Profile,
    PullAction,
    PullRequest,
    PullResult,
    PushAction,
    PushRequest,
    PushResult,
    ShowRequest,
    ShowResult,
    SprintRequest,
    SprintResult,
    StatusItem,
    StatusRequest,
    StatusResult,
)
from .project_config import load_project_config
from .profile_loader import load_profile, update_profile_field_aliases
from .state_store import load_state, save_state
from .status_engine import compute_field_hash, compute_status


class JiraTicketSyncService:
    def __init__(
        self,
        *,
        backend_factory: type[JiraBackend] | None = None,
        real_backend_factory: type[CpToolsJiraBackend] | None = None,
    ) -> None:
        self._backend_factory = backend_factory or JiraBackend
        self._real_backend_factory = real_backend_factory or CpToolsJiraBackend

    def status(self, request: StatusRequest) -> StatusResult:
        items: list[StatusItem] = []
        for manifest_path in self._discover_manifest_paths(request.path):
            manifest = load_manifest(manifest_path)
            for ticket in manifest.tickets:
                status = compute_status(None, None, None) if ticket.get("jira_key") is None else "in_sync"
                items.append(StatusItem(manifest_path=manifest_path, local_id=ticket["local_id"], status=status))
        return StatusResult(items=items)

    def show_issue(self, request: ShowRequest) -> ShowResult:
        if not request.use_real:
            raise ValueError("show requires --real")

        project_key = request.ticket.split("-")[0] if request.ticket else "UNKNOWN"
        backend = self._build_backend(True, request.jira_project_config_path)
        issue = backend.fetch_issue(request.ticket, project_key=project_key)
        fields = issue.get("fields", {})

        custom_fields = {
            key: value
            for key, value in fields.items()
            if key.startswith("customfield_") and value is not None
        }
        if request.profile_path is not None:
            profile = load_profile(request.profile_path)
            custom_fields = self._map_custom_fields_to_aliases(custom_fields, profile)

        summary = {
            "summary": fields.get("summary"),
            "description": fields.get("description"),
            "issue_type": fields.get("issuetype", {}).get("name"),
            "status": fields.get("status", {}).get("name"),
            "priority": fields.get("priority", {}).get("name"),
            "assignee": self._extract_assignee(fields.get("assignee")),
            "labels": fields.get("labels", []),
            "fields": custom_fields,
        }

        return ShowResult(
            ticket=issue.get("key", request.ticket),
            project_key=project_key,
            summary={key: value for key, value in summary.items() if value is not None},
        )

    def push(self, request: PushRequest) -> PushResult:
        backend = self._build_backend(request.use_real, request.jira_project_config_path)
        actions: list[PushAction] = []
        for manifest_path in self._discover_manifest_paths(request.path):
            manifest = load_manifest(manifest_path)
            for ticket in manifest.tickets:
                if request.use_real:
                    profile = self._load_manifest_profile(
                        manifest_path,
                        manifest.manifest.get("profile", ""),
                        request.profile_root,
                    )
                    resolved = resolve_ticket(manifest, profile, ticket["local_id"])
                    operation = build_operation_plan(resolved, profile)
                    if request.dry_run:
                        actions.append(PushAction(manifest_path=manifest_path, local_id=ticket["local_id"], action=operation["mode"].upper()))
                        continue

                    result = backend.apply_operation(operation)
                    if result["mode"] == "create":
                        update_ticket_in_manifest(manifest_path, ticket["local_id"], {"jira_key": result["key"]})
                    self._record_sync_state(request.state_file, manifest_path, ticket["local_id"], resolved.data)
                    actions.append(
                        PushAction(
                            manifest_path=manifest_path,
                            local_id=ticket["local_id"],
                            action=result["mode"].upper(),
                            jira_key=result["key"],
                            dropped_fields=result.get("dropped_fields", []),
                            follow_up_error=result.get("follow_up_error"),
                        )
                    )
                    continue

                action = backend.preview_push_action(ticket)
                actions.append(PushAction(manifest_path=manifest_path, local_id=ticket["local_id"], action=action))
        return PushResult(actions=actions)

    def pull(self, request: PullRequest) -> PullResult:
        backend = self._build_backend(request.use_real, request.jira_project_config_path)
        actions: list[PullAction] = []
        for manifest_path in self._discover_manifest_paths(request.path):
            manifest = load_manifest(manifest_path)
            for ticket in manifest.tickets:
                jira_key = ticket.get("jira_key")
                if jira_key is None:
                    continue
                if request.use_real:
                    profile = self._load_manifest_profile(
                        manifest_path,
                        manifest.manifest.get("profile", ""),
                        request.profile_root,
                    )
                    issue = backend.fetch_issue(jira_key, project_key=profile.project)
                    if not request.dry_run:
                        updates = self._build_pull_updates(issue, profile)
                        update_ticket_in_manifest(manifest_path, ticket["local_id"], updates)
                        self._record_sync_state(request.state_file, manifest_path, ticket["local_id"], updates)
                actions.append(
                    PullAction(
                        manifest_path=manifest_path,
                        local_id=ticket["local_id"],
                        jira_key=jira_key,
                        dry_run=request.dry_run,
                    )
                )
        return PullResult(actions=actions)

    def import_issues(self, request: ImportRequest) -> ImportResult:
        project_key = request.tickets[0].split("-")[0] if request.tickets else "UNKNOWN"
        classification_path = request.field_classification_cache_path
        if classification_path is None and request.field_classification_root is not None:
            classification_path = request.field_classification_root / f"{project_key}.json"
        confirmed_classifications = (
            load_field_classifications(classification_path) if classification_path is not None else {}
        )

        if request.use_real and request.tickets:
            backend = self._build_backend(True, request.jira_project_config_path)
            field_schema = backend.fetch_field_schema(project_key)
            aliases = extract_field_aliases(field_schema)
            reverse_aliases = {field_id: alias for alias, field_id in aliases.items()}
            if request.profile_path is not None:
                update_profile_field_aliases(request.profile_path, aliases)
            issues = []
            for ticket in request.tickets:
                issue = backend.fetch_issue(ticket, project_key=project_key)
                fields = issue.get("fields", {})
                issues.append(
                    {
                        "source": ticket,
                        "project": issue["key"].split("-")[0],
                        "summary": fields.get("summary"),
                        "description": fields.get("description"),
                        "priority": fields.get("priority", {}).get("name"),
                        "issue_type": fields.get("issuetype", {}).get("name"),
                        "labels": fields.get("labels", []),
                        "fields": {
                            key: value
                            for key, value in fields.items()
                            if key.startswith("customfield_") and value is not None
                        },
                    }
                )
            template = build_import_template(
                issues,
                reverse_aliases,
                confirmed_classifications=confirmed_classifications,
            )
        else:
            issues = [{"source": ticket, "project": ticket.split("-")[0], "fields": {}} for ticket in request.tickets]
            template = build_import_template(
                issues,
                {},
                confirmed_classifications=confirmed_classifications,
            )

        return ImportResult(
            tickets=request.tickets,
            dry_run=request.dry_run,
            classification_path=classification_path,
            template=template,
        )

    def list_sprints(self, request: SprintRequest) -> SprintResult:
        backend = self._build_backend(request.use_real, request.jira_project_config_path)
        project_config = load_project_config(request.project_key, request.jira_project_config_path)
        effective_board_id = request.board_id if request.board_id is not None else project_config.board_id
        sprints = backend.list_sprints(
            project_key=request.project_key,
            board_id=effective_board_id,
            state=request.state,
        )
        effective_name_prefix = request.name_prefix or project_config.sprint_name_prefix
        if effective_name_prefix:
            sprints = [sprint for sprint in sprints if sprint.get("name", "").startswith(effective_name_prefix)]
        return SprintResult(sprints=sprints)

    def list_epics(self, request: EpicRequest) -> EpicResult:
        backend = self._build_backend(request.use_real, request.jira_project_config_path)
        project_config = load_project_config(request.project_key, request.jira_project_config_path)
        team_field_id = None
        if request.profile_path is not None:
            profile = load_profile(request.profile_path)
            team_field_id = profile.field_aliases.get("team_keys")
        effective_team_key = request.team_key or project_config.team_key or ""
        epics = backend.list_epics(
            project_key=request.project_key,
            team_key=effective_team_key,
            active_only=request.active_only,
            max_results=request.max_results,
            team_field_id=team_field_id,
        )
        return EpicResult(epics=epics)

    def _build_backend(self, use_real: bool, jira_project_config_path: Path | None) -> JiraBackend:
        if use_real:
            try:
                return self._real_backend_factory(project_config_path=jira_project_config_path)
            except TypeError:
                return self._real_backend_factory()
        return self._backend_factory()

    def _load_manifest_profile(self, manifest_path: Path, profile_name: str, profile_root: Path | None) -> Profile:
        if profile_root is not None:
            return load_profile(profile_root / f"{profile_name}.yaml")
        derived_root = self._derive_workspace_root(manifest_path)
        if derived_root is None:
            raise ValueError(f"Cannot derive profile root for manifest: {manifest_path}")
        return load_profile(derived_root / "profiles" / f"{profile_name}.yaml")

    def _discover_manifest_paths(self, path: Path) -> list[Path]:
        if path.is_dir():
            return sorted(candidate for candidate in path.rglob("*.yaml") if candidate.is_file())
        return [path]

    def _record_sync_state(
        self,
        explicit_state_file: Path | None,
        manifest_path: Path,
        local_id: str,
        payload: dict[str, Any],
    ) -> None:
        state_path = explicit_state_file or self._default_state_path(manifest_path)
        if state_path is None:
            return
        state = load_state(state_path)
        key = f"{manifest_path}:{local_id}"
        state.setdefault("tickets", {})[key] = {
            "field_hash": compute_field_hash(payload),
            "status": "in_sync",
        }
        save_state(state_path, state)

    def _default_state_path(self, manifest_path: Path) -> Path | None:
        derived_root = self._derive_workspace_root(manifest_path)
        if derived_root is None:
            return None
        return derived_root / "state" / "sync-state.json"

    def _derive_workspace_root(self, manifest_path: Path) -> Path | None:
        for candidate in [manifest_path.parent, *manifest_path.parents]:
            if candidate.name == "manifests":
                return candidate.parent
        return None

    def _build_pull_updates(self, issue: dict[str, Any], profile: Profile) -> dict[str, Any]:
        fields = issue.get("fields", {})
        managed_fields = set(profile.managed_fields)
        include_all_alias_fields = not managed_fields
        if include_all_alias_fields:
            managed_fields.update({"summary", "description", "labels", "assignee", "priority"})
        updates: dict[str, Any] = {}

        top_level_values = {
            "summary": fields.get("summary"),
            "description": fields.get("description"),
            "labels": fields.get("labels"),
            "assignee": self._extract_assignee(fields.get("assignee")),
            "priority": self._extract_priority(fields.get("priority")),
        }

        for field_name in managed_fields:
            if field_name.startswith("fields."):
                continue
            value = top_level_values.get(field_name, fields.get(field_name))
            if value is not None:
                updates[field_name] = value

        custom_fields: dict[str, Any] = {}
        if include_all_alias_fields:
            for alias, field_id in profile.field_aliases.items():
                value = fields.get(field_id)
                if value is not None:
                    custom_fields[alias] = value
        for field_name in managed_fields:
            if not field_name.startswith("fields."):
                continue
            alias = field_name.split(".", 1)[1]
            field_id = profile.field_aliases.get(alias)
            if field_id is None:
                continue
            if fields.get(field_id) is not None:
                custom_fields[alias] = fields[field_id]
        if custom_fields:
            updates["fields"] = custom_fields

        return updates

    def _extract_assignee(self, assignee: Any) -> Any:
        if isinstance(assignee, dict):
            return assignee.get("name") or assignee.get("displayName") or assignee.get("accountId")
        return assignee

    def _extract_priority(self, priority: Any) -> Any:
        if isinstance(priority, dict):
            return priority.get("name")
        return priority

    def _map_custom_fields_to_aliases(self, custom_fields: dict[str, Any], profile: Profile) -> dict[str, Any]:
        alias_by_field_id = {field_id: alias for alias, field_id in profile.field_aliases.items()}
        return {
            alias_by_field_id.get(field_id, field_id): value
            for field_id, value in custom_fields.items()
        }
