from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

from cptools_jira_ticket_sync.models import ShowRequest
from cptools_jira_ticket_sync.service import JiraTicketSyncService


class _FakeBackend:
    def __init__(self, *_args, **_kwargs) -> None:
        self.calls: list[tuple[str, str]] = []

    def fetch_issue(self, issue_key: str, *, project_key: str) -> dict[str, object]:
        self.calls.append((issue_key, project_key))
        return {
            "key": issue_key,
            "fields": {
                "summary": "Example summary",
                "description": "Example description",
                "issuetype": {"name": "Task"},
                "status": {"name": "In Progress"},
                "priority": {"name": "High"},
                "labels": ["alpha", "beta"],
                "assignee": {"displayName": "Paynter Chen"},
                "customfield_12345": "TEAM-32036",
            },
        }


def test_show_issue_returns_human_summary() -> None:
    service = JiraTicketSyncService(real_backend_factory=_FakeBackend)

    result = service.show_issue(
        ShowRequest(
            ticket="IVAS-1234",
            use_real=True,
        )
    )

    assert result.ticket == "IVAS-1234"
    assert result.project_key == "IVAS"
    assert result.summary["summary"] == "Example summary"
    assert result.summary["status"] == "In Progress"
    assert result.summary["issue_type"] == "Task"
    assert result.summary["assignee"] == "Paynter Chen"
    assert result.summary["labels"] == ["alpha", "beta"]
    assert result.summary["fields"]["customfield_12345"] == "TEAM-32036"


def test_show_issue_uses_profile_aliases_for_custom_fields() -> None:
    service = JiraTicketSyncService(real_backend_factory=_FakeBackend)

    with tempfile.TemporaryDirectory() as tmpdir:
        profile_path = Path(tmpdir) / "IVAS.yaml"
        profile_path.write_text(
            textwrap.dedent(
                """
                profile:
                  id: IVAS
                  project: IVAS
                  field_aliases:
                    team_keys: customfield_12345
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        result = service.show_issue(
            ShowRequest(
                ticket="IVAS-1234",
                use_real=True,
                profile_path=profile_path,
            )
        )

    assert result.summary["fields"]["team_keys"] == "TEAM-32036"
    assert "customfield_12345" not in result.summary["fields"]
