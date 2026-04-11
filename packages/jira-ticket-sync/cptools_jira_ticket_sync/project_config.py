from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ProjectConfig:
    project_key: str
    epic_name_field: str | None = None
    epic_link_field: str | None = None
    parent_link_field: str | None = None
    sprint_field: str | None = None
    story_points_field: str | None = None
    team_field: str | None = None
    board_id: int | None = None
    sprint_name_prefix: str | None = None
    team_key: str | None = None
    issue_type_names: dict[str, str] = field(
        default_factory=lambda: {
            "epic": "Epic",
            "initiative": "Initiative",
            "story": "User Story",
            "task": "Task",
            "bug": "Bug",
            "subtask": "Sub-task",
        }
    )

    def get_issue_type_name(self, issue_type: str) -> str:
        normalized = issue_type.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
        return self.issue_type_names.get(normalized, issue_type)

    @classmethod
    def from_dict(cls, project_key: str, data: dict[str, Any]) -> "ProjectConfig":
        fields = data.get("fields", {})
        issue_types = data.get("issue_types", {})
        queries = data.get("queries", {})
        return cls(
            project_key=project_key,
            epic_name_field=fields.get("epic_name"),
            epic_link_field=fields.get("epic_link"),
            parent_link_field=fields.get("parent_link"),
            sprint_field=fields.get("sprint"),
            story_points_field=fields.get("story_points"),
            team_field=fields.get("team"),
            board_id=queries.get("board_id"),
            sprint_name_prefix=queries.get("sprint_name_prefix"),
            team_key=queries.get("team_key"),
            issue_type_names={
                "epic": "Epic",
                "initiative": issue_types.get("initiative", "Initiative"),
                "story": issue_types.get("story", "User Story"),
                "task": "Task",
                "bug": "Bug",
                "subtask": issue_types.get("subtask", "Sub-task"),
            },
        )


def load_project_config(project_key: str, config_path: Path | None = None) -> ProjectConfig:
    effective_path = config_path
    if effective_path is None:
        configured = os.getenv("JIRA_PROJECT_CONFIG_PATH")
        if configured:
            effective_path = Path(configured)

    if effective_path is None or not effective_path.exists():
        return ProjectConfig(project_key=project_key)

    with effective_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    projects = raw.get("projects", {})
    project_data = projects.get(project_key)
    if not isinstance(project_data, dict):
        return ProjectConfig(project_key=project_key)
    return ProjectConfig.from_dict(project_key, project_data)
