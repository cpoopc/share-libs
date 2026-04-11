from __future__ import annotations

import contextlib
from io import StringIO
from pathlib import Path

from requests import ConnectionError as RequestsConnectionError

from cptools_jira_ticket_sync.cli import main
from cptools_jira_ticket_sync.retry import run_with_backoff
from cptools_jira_ticket_sync import service as service_module


def _write_real_env(root: Path) -> Path:
    env_path = root / ".env"
    env_path.write_text(
        "\n".join(
            [
                "JIRA_URL=https://jira.ringcentral.com",
                "JIRA_USE_BEARER=true",
                "JIRA_TOKEN=real-token",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return env_path


def test_status_command_lists_ticket_state(tmp_path: Path) -> None:
    manifests_dir = tmp_path / "manifests"
    nested_dir = manifests_dir / "sprint"
    nested_dir.mkdir(parents=True)
    (nested_dir / "sprint.yaml").write_text(
        "\n".join(
            [
                "manifest:",
                "  id: sprint-2026-sp02-observability",
                "  kind: sprint",
                "  profile: IVAS",
                "tickets:",
                "  - local_id: nova-unstable-alert-gap",
                "    jira_key: null",
                "    issue_type: Task",
                "    summary: Add missed alert for NOVA unstable",
                "    description: Create alert coverage for the current NOVA unstable gap.",
            ]
        ),
        encoding="utf-8",
    )

    output = StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = main(["status", str(manifests_dir)])

    rendered = output.getvalue()
    assert exit_code == 0
    assert "nova-unstable-alert-gap" in rendered
    assert "draft" in rendered


def test_retry_on_rate_limit_then_succeed() -> None:
    responses = iter([429, 200])
    calls = {"count": 0}

    def flaky_operation() -> int:
        calls["count"] += 1
        return next(responses)

    result = run_with_backoff(flaky_operation, is_retryable=lambda code: code == 429)

    assert result == 200
    assert calls["count"] == 2


def test_push_dry_run_prints_create_and_update_actions(tmp_path: Path) -> None:
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    (manifests_dir / "sprint.yaml").write_text(
        "\n".join(
            [
                "manifest:",
                "  id: sprint-2026-sp02-observability",
                "  kind: sprint",
                "  profile: IVAS",
                "tickets:",
                "  - local_id: new-ticket",
                "    jira_key: null",
                "    issue_type: Task",
                "    summary: New ticket",
                "    description: New ticket description.",
                "  - local_id: existing-ticket",
                "    jira_key: IVAS-6701",
                "    issue_type: Task",
                "    summary: Existing ticket",
                "    description: Existing ticket description.",
            ]
        ),
        encoding="utf-8",
    )

    output = StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = main(["push", str(manifests_dir), "--dry-run"])

    rendered = output.getvalue()
    assert exit_code == 0
    assert "CREATE new-ticket" in rendered
    assert "UPDATE existing-ticket" in rendered


def test_pull_dry_run_prints_ticket_actions(tmp_path: Path) -> None:
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    (manifests_dir / "sprint.yaml").write_text(
        "\n".join(
            [
                "manifest:",
                "  id: sprint-2026-sp02-observability",
                "  kind: sprint",
                "  profile: IVAS",
                "tickets:",
                "  - local_id: existing-ticket",
                "    jira_key: IVAS-6701",
                "    issue_type: Task",
                "    summary: Existing ticket",
                "    description: Existing ticket description.",
            ]
        ),
        encoding="utf-8",
    )

    output = StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = main(["pull", str(manifests_dir), "--dry-run"])

    rendered = output.getvalue()
    assert exit_code == 0
    assert "PULL existing-ticket" in rendered


def test_import_dry_run_prints_inferred_common_fields() -> None:
    output = StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = main(["import", "IVAS-6699", "IVAS-6698", "--dry-run"])

    rendered = output.getvalue()
    assert exit_code == 0
    assert "IVAS-6699" in rendered
    assert "IVAS-6698" in rendered


def test_import_real_reports_connection_failure(tmp_path: Path, monkeypatch) -> None:
    env_path = _write_real_env(tmp_path)

    class FailingBackend:
        def fetch_field_schema(self, project_key: str):
            raise RequestsConnectionError("dns failed")

    monkeypatch.setattr(service_module, "CpToolsJiraBackend", FailingBackend)

    output = StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = main(["--env-file", str(env_path), "import", "IVAS-6699", "--dry-run", "--real"])

    rendered = output.getvalue()
    assert exit_code == 2
    assert "Real Jira backend failed" in rendered


def test_push_real_writes_created_jira_key_back_to_manifest(tmp_path: Path, monkeypatch) -> None:
    _write_real_env(tmp_path)

    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    profiles_dir.joinpath("IVAS.yaml").write_text(
        "\n".join(
            [
                "profile:",
                "  id: IVAS",
                "  project: IVAS",
            ]
        ),
        encoding="utf-8",
    )
    manifests_dir = tmp_path / "manifests"
    nested_dir = manifests_dir / "sprint"
    nested_dir.mkdir(parents=True)
    manifest_path = nested_dir / "sprint.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "manifest:",
                "  id: sprint-2026-sp02-observability",
                "  kind: sprint",
                "  profile: IVAS",
                "tickets:",
                "  - local_id: new-ticket",
                "    jira_key: null",
                "    issue_type: Task",
                "    summary: New ticket",
                "    description: New ticket description.",
            ]
        ),
        encoding="utf-8",
    )

    class FakeBackend:
        def apply_operation(self, operation):
            return {"mode": "create", "key": "IVAS-9999"}

    monkeypatch.setattr(service_module, "CpToolsJiraBackend", FakeBackend)

    exit_code = main(["push", str(manifests_dir), "--real"])

    assert exit_code == 0
    assert "jira_key: IVAS-9999" in manifest_path.read_text(encoding="utf-8")


def test_pull_real_writes_remote_fields_back_to_manifest(tmp_path: Path, monkeypatch) -> None:
    _write_real_env(tmp_path)

    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    profiles_dir.joinpath("IVAS.yaml").write_text(
        "\n".join(
            [
                "profile:",
                "  id: IVAS",
                "  project: IVAS",
                "  field_aliases:",
                "    team: customfield_10012",
            ]
        ),
        encoding="utf-8",
    )
    manifests_dir = tmp_path / "manifests"
    nested_dir = manifests_dir / "sprint"
    nested_dir.mkdir(parents=True)
    manifest_path = nested_dir / "sprint.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "manifest:",
                "  id: sprint-2026-sp02-observability",
                "  kind: sprint",
                "  profile: IVAS",
                "tickets:",
                "  - local_id: existing-ticket",
                "    jira_key: IVAS-6701",
                "    issue_type: Task",
                "    summary: Old summary",
                "    description: Old description.",
                "    notes: keep-local",
            ]
        ),
        encoding="utf-8",
    )

    class FakeBackend:
        def fetch_issue(self, issue_key: str, *, project_key: str):
            return {
                "key": issue_key,
                "fields": {
                    "summary": "New summary",
                    "description": "New description.",
                    "assignee": {"name": "paynter.chen"},
                    "priority": {"name": "High"},
                    "labels": ["observability"],
                    "customfield_10012": "AIR",
                },
            }

    monkeypatch.setattr(service_module, "CpToolsJiraBackend", FakeBackend)

    exit_code = main(["pull", str(manifests_dir), "--real"])

    text = manifest_path.read_text(encoding="utf-8")
    assert exit_code == 0
    assert "summary: New summary" in text
    assert "description: New description." in text
    assert "assignee: paynter.chen" in text
    assert "priority: High" in text
    assert "team: AIR" in text
    assert "notes: keep-local" in text


def test_import_real_can_write_field_aliases_to_profile(tmp_path: Path, monkeypatch) -> None:
    _write_real_env(tmp_path)

    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir(parents=True)
    profile_path = profile_dir / "IVAS.yaml"
    profile_path.write_text(
        "\n".join(
            [
                "profile:",
                "  id: IVAS",
                "  project: IVAS",
                "  field_aliases: {}",
            ]
        ),
        encoding="utf-8",
    )

    class FakeBackend:
        def fetch_field_schema(self, project_key: str):
            return [{"id": "customfield_10012", "name": "Team", "custom": True}]

        def fetch_issue(self, issue_key: str, *, project_key: str):
            return {
                "key": issue_key,
                "fields": {
                    "summary": "Example",
                    "customfield_10012": "AIR",
                },
            }

    monkeypatch.setattr(service_module, "CpToolsJiraBackend", FakeBackend)

    output = StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = main(
            [
                "import",
                "IVAS-6699",
                "--dry-run",
                "--real",
                "--profile",
                str(profile_path),
            ]
        )

    rendered = output.getvalue()
    assert exit_code == 0
    assert "team" in rendered
    assert "customfield_10012" in profile_path.read_text(encoding="utf-8")


def test_import_real_applies_field_classification_cache(tmp_path: Path, monkeypatch) -> None:
    env_path = _write_real_env(tmp_path)
    cache_dir = tmp_path / "field-classification"
    cache_dir.mkdir(parents=True)
    cache_path = cache_dir / "IVAS.json"
    cache_path.write_text(
        "\n".join(
            [
                "{",
                '  "project": "IVAS",',
                '  "fields": {',
                '    "team": {',
                '      "classification": "ui_noise",',
                '      "action": "drop",',
                '      "confidence": 0.99,',
                '      "reason": "ignore",',
                '      "suggested_for": []',
                "    }",
                "  }",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    class FakeBackend:
        def fetch_field_schema(self, project_key: str):
            return [{"id": "customfield_10012", "name": "Team", "custom": True}]

        def fetch_issue(self, issue_key: str, *, project_key: str):
            return {
                "key": issue_key,
                "fields": {
                    "summary": "Example",
                    "issuetype": {"name": "Bug"},
                    "customfield_10012": "AIR",
                },
            }

    monkeypatch.setattr(service_module, "CpToolsJiraBackend", FakeBackend)

    output = StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = main(
            [
                "import",
                "IVAS-6699",
                "--env-file",
                str(env_path),
                "--dry-run",
                "--real",
                "--field-classification-cache",
                str(cache_path),
            ]
        )

    rendered = output.getvalue()
    assert exit_code == 0
    assert "field classification cache" in rendered
    assert "confirmed_drop" in rendered


def test_sprints_real_lists_recent_sprints(tmp_path: Path, monkeypatch) -> None:
    env_path = _write_real_env(tmp_path)

    class FakeBackend:
        def list_sprints(self, *, project_key: str, board_id: int | None, state: str):
            assert project_key == "IVAS"
            assert board_id == 7412
            assert state == "active,future"
            return [
                {"id": 36651, "name": "Nova26: 03/09-03/20", "state": "active"},
                {"id": 36907, "name": "AIR2606(0309-0322)", "state": "active"},
                {"id": 36908, "name": "AIR2607(0323-0405)", "state": "future"},
            ]

    monkeypatch.setattr(service_module, "CpToolsJiraBackend", FakeBackend)

    output = StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = main(
            [
                "--env-file",
                str(env_path),
                "sprints",
                "--project",
                "IVAS",
                "--board-id",
                "7412",
                "--name-prefix",
                "AIR",
                "--real",
            ]
        )

    rendered = output.getvalue()
    assert exit_code == 0
    assert "36907" in rendered
    assert "AIR2606(0309-0322)" in rendered
    assert "active" in rendered
    assert "36908" in rendered
    assert "future" in rendered
    assert "Nova26" not in rendered


def test_sprints_real_uses_project_config_defaults(tmp_path: Path, monkeypatch) -> None:
    _write_real_env(tmp_path)

    config_path = tmp_path / "jira-projects.yaml"
    config_path.write_text(
        "\n".join(
            [
                "projects:",
                "  IVAS:",
                "    queries:",
                "      board_id: 7412",
                "      sprint_name_prefix: AIR",
            ]
        ),
        encoding="utf-8",
    )

    class FakeBackend:
        def list_sprints(self, *, project_key: str, board_id: int | None, state: str):
            assert project_key == "IVAS"
            assert board_id == 7412
            assert state == "active,future"
            return [
                {"id": 36651, "name": "Nova26: 03/09-03/20", "state": "active"},
                {"id": 36907, "name": "AIR2606(0309-0322)", "state": "active"},
            ]

    monkeypatch.setattr(service_module, "CpToolsJiraBackend", FakeBackend)

    output = StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = main(
            [
                "sprints",
                "--project",
                "IVAS",
                "--real",
                "--jira-project-config",
                str(config_path),
            ]
        )

    rendered = output.getvalue()
    assert exit_code == 0
    assert "36907" in rendered
    assert "AIR2606(0309-0322)" in rendered
    assert "Nova26" not in rendered


def test_epics_real_lists_team_epics(tmp_path: Path, monkeypatch) -> None:
    _write_real_env(tmp_path)

    profile_path = tmp_path / "IVAS.yaml"
    profile_path.write_text(
        "\n".join(
            [
                "profile:",
                "  id: IVAS",
                "  project: IVAS",
                "  field_aliases:",
                "    team_keys: customfield_28351",
            ]
        ),
        encoding="utf-8",
    )

    class FakeBackend:
        def list_epics(
            self,
            *,
            project_key: str,
            team_key: str,
            active_only: bool,
            max_results: int,
            team_field_id: str | None = None,
        ):
            assert project_key == "IVAS"
            assert team_key == "TEAM-32036"
            assert active_only is False
            assert max_results == 20
            assert team_field_id == "customfield_28351"
            return [
                {
                    "key": "IVAS-5791",
                    "summary": "User experience improvements Q1'26",
                    "status": "To Do",
                    "url": "https://jira.ringcentral.com/browse/IVAS-5791",
                }
            ]

    monkeypatch.setattr(service_module, "CpToolsJiraBackend", FakeBackend)

    output = StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = main(
            [
                "epics",
                "--project",
                "IVAS",
                "--team",
                "TEAM-32036",
                "--profile",
                str(profile_path),
                "--real",
            ]
        )

    rendered = output.getvalue()
    assert exit_code == 0
    assert "IVAS-5791" in rendered
    assert "User experience improvements Q1'26" in rendered
    assert "To Do" in rendered
    assert "https://jira.ringcentral.com/browse/IVAS-5791" in rendered


def test_epics_real_uses_project_config_team_default(tmp_path: Path, monkeypatch) -> None:
    _write_real_env(tmp_path)

    config_path = tmp_path / "jira-projects.yaml"
    config_path.write_text(
        "\n".join(
            [
                "projects:",
                "  IVAS:",
                "    fields:",
                "      team: customfield_28351",
                "    queries:",
                "      team_key: TEAM-32036",
            ]
        ),
        encoding="utf-8",
    )

    class FakeBackend:
        def list_epics(
            self,
            *,
            project_key: str,
            team_key: str,
            active_only: bool,
            max_results: int,
            team_field_id: str | None = None,
        ):
            assert project_key == "IVAS"
            assert team_key == "TEAM-32036"
            assert active_only is True
            assert max_results == 20
            assert team_field_id is None
            return [
                {
                    "key": "IVAS-5791",
                    "summary": "User experience improvements Q1'26",
                    "status": "To Do",
                    "url": "https://jira.ringcentral.com/browse/IVAS-5791",
                }
            ]

    monkeypatch.setattr(service_module, "CpToolsJiraBackend", FakeBackend)

    output = StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = main(
            [
                "epics",
                "--project",
                "IVAS",
                "--active-only",
                "--real",
                "--jira-project-config",
                str(config_path),
            ]
        )

    rendered = output.getvalue()
    assert exit_code == 0
    assert "IVAS-5791" in rendered
