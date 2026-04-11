from __future__ import annotations

from cptools_jira_ticket_sync.jira_backend import CpToolsJiraBackend, build_operation_plan, extract_field_aliases
from cptools_jira_ticket_sync.models import Profile, ResolvedTicket


def test_extract_field_aliases_from_jira_field_schema() -> None:
    field_schema = [
        {"id": "customfield_10012", "name": "Team", "custom": True},
        {"id": "customfield_10105", "name": "Product Area", "custom": True},
        {"id": "summary", "name": "Summary", "custom": False},
    ]

    aliases = extract_field_aliases(field_schema)

    assert aliases["team"] == "customfield_10012"
    assert aliases["product_area"] == "customfield_10105"
    assert "summary" not in aliases


def test_build_operation_plan_maps_aliases_and_hierarchy_fields() -> None:
    profile = Profile(
        id="IVAS",
        project="IVAS",
        field_aliases={"team": "customfield_10012"},
    )
    ticket = ResolvedTicket(
        data={
            "local_id": "nova-unstable-alert-gap",
            "jira_key": None,
            "issue_type": "Task",
            "summary": "Add missed alert for NOVA unstable",
            "description": "Create alert coverage for the current NOVA unstable gap.",
            "priority": "Medium",
            "labels": ["observability"],
            "assignee": "paynter.chen",
            "epic_key": "IVAS-6784",
            "fields": {"team": "NOVA"},
        }
    )

    operation = build_operation_plan(ticket, profile)

    assert operation["mode"] == "create"
    assert operation["project"] == "IVAS"
    assert operation["summary"] == "Add missed alert for NOVA unstable"
    assert operation["custom_fields"]["customfield_10012"] == "NOVA"
    assert operation["epic_key"] == "IVAS-6784"


def test_apply_operation_create_performs_follow_up_field_update() -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeSession:
        def __init__(self) -> None:
            self.put_calls: list[tuple[str, dict]] = []

        def put(self, url: str, json: dict):
            self.put_calls.append((url, json))
            return FakeResponse()

    class FakeClient:
        def __init__(self) -> None:
            self.base_url = "https://jira.example.com"
            self.session = FakeSession()
            self.create_calls: list[dict] = []
            self.sprint_calls: list[tuple[int, list[str]]] = []

        def create_issue(self, **kwargs):
            self.create_calls.append(kwargs)
            return {"key": "IVAS-9999"}

        def add_issues_to_sprint(self, sprint_id: int, issue_keys: list[str]) -> bool:
            self.sprint_calls.append((sprint_id, issue_keys))
            return True

    class FakeConfig:
        epic_link_field = "customfield_11450"
        parent_link_field = "customfield_15751"
        sprint_field = "customfield_10652"
        epic_name_field = "customfield_11451"

        def get_issue_type_name(self, issue_type: str) -> str:
            return "Task" if issue_type == "task" else issue_type

    backend = CpToolsJiraBackend.__new__(CpToolsJiraBackend)
    fake_client = FakeClient()
    fake_config = FakeConfig()
    backend._get_client = lambda project_key: (fake_client, fake_config)  # type: ignore[method-assign]

    result = backend.apply_operation(
        {
            "mode": "create",
            "project": "IVAS",
            "issue_type": "Task",
            "summary": "Example",
            "description": "Desc",
            "priority": "Normal",
            "labels": [],
            "assignee": "Paynter.Chen",
            "epic_key": "IVAS-5793",
            "initiative_key": None,
            "sprint_id": 36907,
            "custom_fields": {"customfield_28351": "TEAM-32036"},
        }
    )

    assert result["mode"] == "create"
    assert result["key"] == "IVAS-9999"

    assert len(fake_client.create_calls) == 1
    create_call = fake_client.create_calls[0]
    assert create_call["assignee"] is None
    assert create_call["custom_fields"] is None

    assert len(fake_client.session.put_calls) == 1
    put_url, put_payload = fake_client.session.put_calls[0]
    assert put_url.endswith("/rest/api/2/issue/IVAS-9999")
    assert put_payload["fields"]["assignee"] == {"name": "Paynter.Chen"}
    assert put_payload["fields"]["customfield_28351"] == "TEAM-32036"
    assert put_payload["fields"]["customfield_11450"] == "IVAS-5793"
    assert fake_client.sprint_calls == [(36907, ["IVAS-9999"])]


def test_apply_operation_create_retries_without_rejected_field() -> None:
    class FakeResponse:
        def __init__(self, status_code: int, payload: dict | None = None) -> None:
            self.status_code = status_code
            self._payload = payload or {}
            self.ok = status_code < 400

        def raise_for_status(self) -> None:
            if not self.ok:
                raise RuntimeError("http error")

        def json(self) -> dict:
            return self._payload

    class FakeSession:
        def __init__(self) -> None:
            self.put_calls: list[tuple[str, dict]] = []

        def put(self, url: str, json: dict):
            self.put_calls.append((url, json))
            if len(self.put_calls) == 1:
                return FakeResponse(
                    400,
                    {"errors": {"customfield_28351": "cannot be set"}, "errorMessages": []},
                )
            return FakeResponse(204, {})

    class FakeClient:
        def __init__(self) -> None:
            self.base_url = "https://jira.example.com"
            self.session = FakeSession()

        def create_issue(self, **kwargs):
            return {"key": "IVAS-9998"}

    class FakeConfig:
        epic_link_field = None
        parent_link_field = None
        sprint_field = None
        epic_name_field = None

        def get_issue_type_name(self, issue_type: str) -> str:
            return "Task" if issue_type == "task" else issue_type

    backend = CpToolsJiraBackend.__new__(CpToolsJiraBackend)
    fake_client = FakeClient()
    fake_config = FakeConfig()
    backend._get_client = lambda project_key: (fake_client, fake_config)  # type: ignore[method-assign]

    result = backend.apply_operation(
        {
            "mode": "create",
            "project": "IVAS",
            "issue_type": "Task",
            "summary": "Example",
            "description": "Desc",
            "priority": "Normal",
            "labels": [],
            "assignee": "Paynter.Chen",
            "epic_key": None,
            "initiative_key": None,
            "sprint_id": None,
            "custom_fields": {"customfield_28351": "TEAM-32036"},
        }
    )

    assert result["key"] == "IVAS-9998"
    assert result["dropped_fields"] == ["customfield_28351"]
    assert len(fake_client.session.put_calls) == 2
    second_payload = fake_client.session.put_calls[1][1]
    assert "customfield_28351" not in second_payload["fields"]
    assert second_payload["fields"]["assignee"] == {"name": "Paynter.Chen"}
