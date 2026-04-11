from __future__ import annotations

from pathlib import Path

from cptools_jira_ticket_sync.manifest_loader import load_manifest, resolve_ticket
from cptools_jira_ticket_sync.profile_loader import load_profile, update_profile_field_aliases


def test_ticket_overrides_manifest_and_profile_defaults(tmp_path: Path) -> None:
    profile_path = tmp_path / "IVAS.yaml"
    profile_path.write_text(
        "\n".join(
            [
                "profile:",
                "  id: IVAS",
                "  project: IVAS",
                "  defaults:",
                "    priority: Low",
                "    labels:",
                "      - ai-sdlc",
                "  managed_fields:",
                "    - summary",
                "    - fields.team",
                "  field_aliases:",
                "    team: customfield_10012",
            ]
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "sprint.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "manifest:",
                "  id: sprint-2026-sp02-observability",
                "  kind: sprint",
                "  profile: IVAS",
                "defaults:",
                "  priority: Medium",
                "  fields:",
                "    team: AIR",
                "tickets:",
                "  - local_id: nova-unstable-alert-gap",
                "    jira_key: null",
                "    issue_type: Task",
                "    summary: Add missed alert for NOVA unstable",
                "    description: Create alert coverage for the current NOVA unstable gap.",
                "    fields:",
                "      team: NOVA",
            ]
        ),
        encoding="utf-8",
    )

    profile = load_profile(profile_path)
    manifest = load_manifest(manifest_path)

    ticket = resolve_ticket(manifest, profile, "nova-unstable-alert-gap")

    assert ticket.priority == "Medium"
    assert ticket.fields["team"] == "NOVA"


def test_update_profile_field_aliases_merges_without_clobbering_defaults(tmp_path: Path) -> None:
    profile_path = tmp_path / "IVAS.yaml"
    profile_path.write_text(
        "\n".join(
            [
                "profile:",
                "  id: IVAS",
                "  project: IVAS",
                "  defaults:",
                "    priority: Medium",
                "  field_aliases:",
                "    team: customfield_10012",
            ]
        ),
        encoding="utf-8",
    )

    update_profile_field_aliases(profile_path, {"product_area": "customfield_10105"})
    profile = load_profile(profile_path)

    assert profile.defaults["priority"] == "Medium"
    assert profile.field_aliases == {
        "team": "customfield_10012",
        "product_area": "customfield_10105",
    }
