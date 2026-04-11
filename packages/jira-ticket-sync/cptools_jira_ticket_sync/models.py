from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Profile:
    id: str
    project: str
    defaults: dict[str, Any] = field(default_factory=dict)
    managed_fields: list[str] = field(default_factory=list)
    field_aliases: dict[str, str] = field(default_factory=dict)
    required_fields: list[str] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)


@dataclass
class ManifestFile:
    path: Path
    manifest: dict[str, Any]
    defaults: dict[str, Any]
    tickets: list[dict[str, Any]]


@dataclass
class ResolvedTicket:
    data: dict[str, Any]

    @property
    def priority(self) -> Any:
        return self.data.get("priority")

    @property
    def fields(self) -> dict[str, Any]:
        return self.data.get("fields", {})


@dataclass
class StatusRequest:
    path: Path


@dataclass
class StatusItem:
    manifest_path: Path
    local_id: str
    status: str


@dataclass
class StatusResult:
    items: list[StatusItem]


@dataclass
class ShowRequest:
    ticket: str
    use_real: bool = False
    profile_path: Path | None = None
    jira_project_config_path: Path | None = None


@dataclass
class ShowResult:
    ticket: str
    project_key: str
    summary: dict[str, Any]


@dataclass
class PushRequest:
    path: Path
    dry_run: bool = False
    use_real: bool = False
    profile_root: Path | None = None
    state_file: Path | None = None
    jira_project_config_path: Path | None = None


@dataclass
class PushAction:
    manifest_path: Path
    local_id: str
    action: str
    jira_key: str | None = None
    dropped_fields: list[str] = field(default_factory=list)
    follow_up_error: str | None = None


@dataclass
class PushResult:
    actions: list[PushAction]


@dataclass
class PullRequest:
    path: Path
    dry_run: bool = False
    use_real: bool = False
    profile_root: Path | None = None
    state_file: Path | None = None
    jira_project_config_path: Path | None = None


@dataclass
class PullAction:
    manifest_path: Path
    local_id: str
    jira_key: str
    dry_run: bool = False


@dataclass
class PullResult:
    actions: list[PullAction]


@dataclass
class ImportRequest:
    tickets: list[str]
    dry_run: bool = False
    use_real: bool = False
    profile_path: Path | None = None
    field_classification_cache_path: Path | None = None
    field_classification_root: Path | None = None
    jira_project_config_path: Path | None = None


@dataclass
class ImportResult:
    tickets: list[str]
    dry_run: bool
    classification_path: Path | None
    template: dict[str, Any]


@dataclass
class SprintRequest:
    project_key: str
    board_id: int | None = None
    state: str = "active,future"
    name_prefix: str | None = None
    use_real: bool = False
    jira_project_config_path: Path | None = None


@dataclass
class SprintResult:
    sprints: list[dict[str, Any]]


@dataclass
class EpicRequest:
    project_key: str
    team_key: str | None = None
    active_only: bool = False
    max_results: int = 20
    use_real: bool = False
    profile_path: Path | None = None
    jira_project_config_path: Path | None = None


@dataclass
class EpicResult:
    epics: list[dict[str, Any]]
