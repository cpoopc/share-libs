from __future__ import annotations

from pathlib import Path
from typing import Any

from cptools_jira import JiraClient, JiraConfig

from .field_aliases import resolve_custom_fields
from .models import Profile, ResolvedTicket
from .project_config import load_project_config


def extract_field_aliases(field_schema: list[dict[str, Any]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for field in field_schema:
        if not field.get("custom"):
            continue
        name = str(field.get("name", "")).strip().lower().replace(" ", "_")
        if not name:
            continue
        aliases[name] = field["id"]
    return aliases


def build_operation_plan(ticket: ResolvedTicket, profile: Profile) -> dict[str, Any]:
    data = ticket.data
    custom_fields = resolve_custom_fields(data.get("fields", {}), profile.field_aliases)
    return {
        "mode": "create" if data.get("jira_key") is None else "update",
        "jira_key": data.get("jira_key"),
        "project": data.get("project", profile.project),
        "issue_type": data.get("issue_type", "Task"),
        "summary": data.get("summary"),
        "description": data.get("description"),
        "priority": data.get("priority"),
        "labels": data.get("labels"),
        "assignee": data.get("assignee"),
        "parent_key": data.get("parent_key"),
        "epic_key": data.get("epic_key"),
        "initiative_key": data.get("initiative_key"),
        "sprint_id": data.get("sprint_id"),
        "custom_fields": custom_fields,
    }


class JiraBackend:
    def preview_push_action(self, ticket: dict[str, Any]) -> str:
        return "CREATE" if ticket.get("jira_key") is None else "UPDATE"

    def preview_pull_action(self, ticket: dict[str, Any]) -> str:
        return "PULL"

    def list_sprints(self, *, project_key: str, board_id: int | None, state: str) -> list[dict[str, Any]]:
        return []

    def list_epics(
        self,
        *,
        project_key: str,
        team_key: str,
        active_only: bool,
        max_results: int,
        team_field_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return []


class CpToolsJiraBackend(JiraBackend):
    def __init__(self, *, project_config_path: Path | None = None) -> None:
        self._project_config_path = project_config_path
        self._clients: dict[str, Any] = {}
        self._configs: dict[str, Any] = {}

    def _get_client(self, project_key: str) -> tuple[Any, Any]:
        if project_key not in self._clients:
            self._clients[project_key] = JiraClient(JiraConfig.from_env())
            self._configs[project_key] = load_project_config(project_key, self._project_config_path)
        return self._clients[project_key], self._configs[project_key]

    def fetch_field_schema(self, project_key: str) -> list[dict[str, Any]]:
        client, _ = self._get_client(project_key)
        response = client.session.get(f"{client.base_url}/rest/api/2/field")
        response.raise_for_status()
        return response.json()

    def fetch_issue(self, issue_key: str, *, project_key: str) -> dict[str, Any]:
        client, _ = self._get_client(project_key)
        return client.get_issue(issue_key)

    def list_sprints(self, *, project_key: str, board_id: int | None, state: str) -> list[dict[str, Any]]:
        client, _ = self._get_client(project_key)
        effective_board_id = board_id
        if effective_board_id is None:
            boards = client.get_boards(project_key)
            if not boards:
                return []
            effective_board_id = int(boards[0]["id"])
        return client.get_sprints(int(effective_board_id), state=state)

    def list_epics(
        self,
        *,
        project_key: str,
        team_key: str,
        active_only: bool,
        max_results: int,
        team_field_id: str | None = None,
    ) -> list[dict[str, Any]]:
        client, config = self._get_client(project_key)
        jql_parts = [
            f"project = {project_key}",
            "issuetype = Epic",
        ]
        if active_only:
            jql_parts.append('statusCategory != Done')
        jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"
        fields = ["summary", "status"]
        if team_field_id:
            fields.append(team_field_id)
        elif config.team_field:
            fields.append(config.team_field)

        issues_result = client.search_all_issues(
            jql,
            fields=fields,
            page_size=max(max_results, 50),
            verbose=False,
        )
        issues = []
        for issue in issues_result:
            fields = issue.get("fields", {})
            team_value = fields.get(team_field_id) if team_field_id else None
            if team_field_id and not _matches_team_key(team_value, team_key):
                continue
            issues.append(
                {
                    "key": issue["key"],
                    "summary": fields.get("summary", ""),
                    "status": fields.get("status", {}).get("name", ""),
                    "url": f"{client.base_url}/browse/{issue['key']}",
                }
            )
            if len(issues) >= max_results:
                break
        return issues

    def apply_operation(self, operation: dict[str, Any]) -> dict[str, Any]:
        client, config = self._get_client(operation["project"])
        custom_fields = dict(operation.get("custom_fields", {}))
        assignee_payload = _build_assignee_field_payload(operation.get("assignee"))
        sprint_id = operation.get("sprint_id")

        issue_type = operation["issue_type"]
        issue_type_name = config.get_issue_type_name(issue_type.lower())
        if operation.get("epic_key") and config.epic_link_field and issue_type_name != "Epic":
            custom_fields[config.epic_link_field] = operation["epic_key"]
        if operation.get("initiative_key") and config.parent_link_field:
            custom_fields[config.parent_link_field] = operation["initiative_key"]
        if issue_type_name == "Epic" and config.epic_name_field:
            custom_fields[config.epic_name_field] = operation["summary"]

        if operation["mode"] == "create":
            create_custom_fields: dict[str, Any] | None = None
            if issue_type_name == "Epic" and config.epic_name_field:
                epic_name_field = config.epic_name_field
                if epic_name_field in custom_fields:
                    create_custom_fields = {epic_name_field: custom_fields.pop(epic_name_field)}
            elif issue_type_name == "Initiative" and custom_fields:
                create_custom_fields = dict(custom_fields)
                custom_fields = {}

            result = client.create_issue(
                project_key=operation["project"],
                summary=operation["summary"],
                issue_type=issue_type_name,
                description=operation.get("description"),
                assignee=None,
                priority=operation.get("priority"),
                labels=operation.get("labels"),
                parent_key=operation.get("parent_key"),
                custom_fields=create_custom_fields,
            )
            issue_key = result.get("key")
            follow_up_fields: dict[str, Any] = {}
            if assignee_payload is not None:
                follow_up_fields["assignee"] = assignee_payload
            if custom_fields:
                follow_up_fields.update(custom_fields)

            follow_up_error = None
            dropped_fields: list[str] = []
            if issue_key and follow_up_fields:
                try:
                    dropped_fields = self._update_issue_fields_best_effort(client, issue_key, follow_up_fields)
                except Exception as exc:
                    follow_up_error = str(exc)
            if issue_key and sprint_id:
                try:
                    client.add_issues_to_sprint(int(sprint_id), [issue_key])
                except Exception as exc:
                    follow_up_error = _join_errors(follow_up_error, f"sprint assignment failed: {exc}")
            return {
                "mode": "create",
                "key": issue_key,
                "result": result,
                "follow_up_error": follow_up_error,
                "dropped_fields": dropped_fields,
            }

        update_fields: dict[str, Any] = {}
        if operation.get("summary") is not None:
            update_fields["summary"] = operation.get("summary")
        if operation.get("description") is not None:
            update_fields["description"] = operation.get("description")
        if operation.get("priority") is not None:
            update_fields["priority"] = {"name": operation.get("priority")}
        if operation.get("labels") is not None:
            update_fields["labels"] = operation.get("labels")
        if assignee_payload is not None:
            update_fields["assignee"] = assignee_payload
        if custom_fields:
            update_fields.update(custom_fields)

        follow_up_error = None
        if update_fields:
            dropped_fields = self._update_issue_fields_best_effort(client, operation["jira_key"], update_fields)
        else:
            dropped_fields = []
        if operation.get("jira_key") and sprint_id:
            try:
                client.add_issues_to_sprint(int(sprint_id), [operation["jira_key"]])
            except Exception as exc:
                follow_up_error = _join_errors(follow_up_error, f"sprint assignment failed: {exc}")
        return {
            "mode": "update",
            "key": operation["jira_key"],
            "result": True,
            "dropped_fields": dropped_fields,
            "follow_up_error": follow_up_error,
        }

    def _update_issue_fields_direct(self, client: Any, issue_key: str, fields: dict[str, Any]) -> None:
        url = f"{client.base_url}/rest/api/2/issue/{issue_key}"
        response = client.session.put(url, json={"fields": fields})
        response.raise_for_status()

    def _update_issue_fields_best_effort(self, client: Any, issue_key: str, fields: dict[str, Any]) -> list[str]:
        pending = dict(fields)
        dropped_fields: list[str] = []
        while pending:
            url = f"{client.base_url}/rest/api/2/issue/{issue_key}"
            response = client.session.put(url, json={"fields": pending})
            if response.ok:
                return dropped_fields
            if response.status_code != 400:
                response.raise_for_status()
            error_fields = self._extract_error_fields(response)
            removable = [field for field in error_fields if field in pending]
            if not removable:
                response.raise_for_status()
            for field in removable:
                pending.pop(field, None)
                dropped_fields.append(field)
        return dropped_fields

    def _extract_error_fields(self, response: Any) -> list[str]:
        try:
            payload = response.json()
        except Exception:
            return []
        errors = payload.get("errors", {})
        if isinstance(errors, dict):
            return list(errors.keys())
        return []


def _matches_team_key(value: Any, team_key: str) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return team_key in value
    if isinstance(value, list):
        return any(_matches_team_key(item, team_key) for item in value)
    if isinstance(value, dict):
        return any(_matches_team_key(item, team_key) for item in value.values())
    return team_key in str(value)


def _build_assignee_field_payload(assignee: Any) -> dict[str, Any] | None:
    if isinstance(assignee, str) and assignee:
        return {"name": assignee}
    if isinstance(assignee, dict):
        return assignee
    return None


def _join_errors(existing: str | None, new_error: str) -> str:
    if existing:
        return f"{existing}; {new_error}"
    return new_error
