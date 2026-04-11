from __future__ import annotations

from cptools_jira_ticket_sync.field_aliases import resolve_custom_fields


def test_profile_alias_maps_manifest_field_to_customfield_id() -> None:
    aliases = {"team": "customfield_10012"}
    payload = resolve_custom_fields({"team": "AIR"}, aliases)

    assert payload == {"customfield_10012": "AIR"}
