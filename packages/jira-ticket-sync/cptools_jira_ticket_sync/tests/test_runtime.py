from __future__ import annotations

import os
from pathlib import Path

from cptools_jira_ticket_sync.runtime import (
    bootstrap_workspace,
    get_runtime_diagnostics,
    init_runtime_home,
    prepare_cli_environment,
    resolve_workspace_paths,
)


def test_resolve_workspace_paths_defaults_to_packaged_assets(monkeypatch) -> None:
    for key in (
        "JIRA_TICKET_SYNC_WORKSPACE_ROOT",
        "JIRA_TICKET_SYNC_MANIFEST_ROOT",
        "JIRA_TICKET_SYNC_PROFILE_ROOT",
        "JIRA_TICKET_SYNC_TEMPLATE_ROOT",
        "JIRA_TICKET_SYNC_PROJECT_CONFIG_PATH",
        "JIRA_TICKET_SYNC_STATE_FILE",
        "JIRA_TICKET_SYNC_FIELD_CLASSIFICATION_ROOT",
    ):
        monkeypatch.delenv(key, raising=False)

    paths = resolve_workspace_paths()

    assert str(paths["manifest_root"]).endswith("/cptools_jira_ticket_sync/assets/workspace/manifests")
    assert str(paths["profile_root"]).endswith("/cptools_jira_ticket_sync/assets/workspace/profiles")
    assert str(paths["template_root"]).endswith("/cptools_jira_ticket_sync/assets/workspace/templates/imported")


def test_resolve_workspace_paths_allows_manifest_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JIRA_TICKET_SYNC_MANIFEST_ROOT", str(tmp_path / "manifests"))

    paths = resolve_workspace_paths()

    assert paths["manifest_root"] == tmp_path / "manifests"


def test_bootstrap_workspace_copies_packaged_assets(tmp_path: Path) -> None:
    target = tmp_path / "workspace"

    messages = bootstrap_workspace(target)

    assert messages == [f"Bootstrapped workspace: {target}"]
    assert (target / ".env.example").exists()
    assert (target / "project-config.yaml").exists()
    assert (target / "profiles" / "IVAS.yaml").exists()
    assert (target / "templates" / "imported" / "IVAS.story.template.yaml").exists()
    assert (target / "state" / "sync-state.json").exists()


def test_init_runtime_home_bootstraps_xdg_workspace(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    paths = init_runtime_home()

    assert paths["config_root"] == tmp_path / "config" / "jira-ticket-sync"
    assert paths["workspace_root"] == tmp_path / "config" / "jira-ticket-sync"
    assert paths["cache_root"] == tmp_path / "cache" / "jira-ticket-sync"
    assert paths["env_path"] == tmp_path / "config" / "jira-ticket-sync" / ".env"
    assert (paths["workspace_root"] / "profiles" / "IVAS.yaml").exists()
    assert (paths["workspace_root"] / "project-config.yaml").exists()


def test_runtime_diagnostics_prefers_xdg_workspace_after_init(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    init_runtime_home()
    diagnostics = get_runtime_diagnostics()

    assert diagnostics["workspace_root"] == tmp_path / "config" / "jira-ticket-sync"
    assert diagnostics["uses_packaged_workspace"] is False
    assert diagnostics["env_exists"] is True


def test_prepare_cli_environment_discovers_workspace_project_config(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "manifests").mkdir(parents=True)
    (workspace / "project-config.yaml").write_text("projects: {}\n", encoding="utf-8")
    (workspace / ".env").write_text(
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

    previous = {
        "JIRA_PROJECT_CONFIG_PATH": os.environ.pop("JIRA_PROJECT_CONFIG_PATH", None),
        "JIRA_URL": os.environ.pop("JIRA_URL", None),
        "JIRA_USE_BEARER": os.environ.pop("JIRA_USE_BEARER", None),
        "JIRA_TOKEN": os.environ.pop("JIRA_TOKEN", None),
    }
    try:
        remaining = prepare_cli_environment(["status", str(workspace / "manifests")])

        assert remaining == ["status", str(workspace / "manifests")]
        assert Path(os.environ["JIRA_PROJECT_CONFIG_PATH"]) == workspace / "project-config.yaml"
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_prepare_cli_environment_allows_explicit_env_without_env_file(monkeypatch) -> None:
    previous = {
        "JIRA_PROJECT_CONFIG_PATH": os.environ.pop("JIRA_PROJECT_CONFIG_PATH", None),
        "JIRA_URL": os.environ.pop("JIRA_URL", None),
        "JIRA_USE_BEARER": os.environ.pop("JIRA_USE_BEARER", None),
        "JIRA_TOKEN": os.environ.pop("JIRA_TOKEN", None),
    }
    monkeypatch.setenv("JIRA_USE_BEARER", "true")
    monkeypatch.setenv("JIRA_TOKEN", "token-from-env")

    try:
        remaining = prepare_cli_environment(["sprints", "--project", "IVAS", "--real"])
        assert remaining == ["sprints", "--project", "IVAS", "--real"]
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
