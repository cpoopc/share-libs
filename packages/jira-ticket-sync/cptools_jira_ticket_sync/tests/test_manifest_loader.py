from __future__ import annotations

from pathlib import Path

from cptools_jira_ticket_sync.manifest_loader import load_manifest, update_ticket_in_manifest


def test_load_manifest_reads_defaults_and_tickets(tmp_path: Path) -> None:
    manifest_path = tmp_path / "sprint.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "manifest:",
                "  id: sprint-2026-sp02-observability",
                "  kind: sprint",
                "  profile: IVAS",
                "defaults:",
                "  sprint_id: 36780",
                "  priority: Medium",
                "tickets:",
                "  - local_id: start-conversation-alert",
                "    jira_key: IVAS-6701",
                "    issue_type: Task",
                "    summary: Start conversation fail alert",
                "    description: Improve alert coverage for start conversation failures.",
            ]
        ),
        encoding="utf-8",
    )

    manifest = load_manifest(manifest_path)

    assert manifest.manifest["kind"] == "sprint"
    assert manifest.defaults["priority"] == "Medium"
    assert manifest.tickets[0]["local_id"] == "start-conversation-alert"


def test_update_ticket_in_manifest_writes_back_selected_fields(tmp_path: Path) -> None:
    manifest_path = tmp_path / "sprint.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "manifest:",
                "  id: sprint-2026-sp02-observability",
                "  kind: sprint",
                "  profile: IVAS",
                "tickets:",
                "  - local_id: start-conversation-alert",
                "    jira_key: null",
                "    issue_type: Task",
                "    summary: Start conversation fail alert",
                "    description: Improve alert coverage.",
                "    notes: keep-local",
            ]
        ),
        encoding="utf-8",
    )

    update_ticket_in_manifest(
        manifest_path,
        "start-conversation-alert",
        {"jira_key": "IVAS-6701", "summary": "Updated summary"},
    )

    manifest = load_manifest(manifest_path)
    assert manifest.tickets[0]["jira_key"] == "IVAS-6701"
    assert manifest.tickets[0]["summary"] == "Updated summary"
    assert manifest.tickets[0]["notes"] == "keep-local"
