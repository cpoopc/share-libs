from __future__ import annotations

from cptools_jira_ticket_sync.import_engine import build_import_template, extract_aliases_from_field_schema


def test_import_builds_review_friendly_template() -> None:
    issues = [
        {
            "source": "IVAS-1",
            "project": "IVAS",
            "issue_type": "Bug",
            "priority": "Medium",
            "fields": {
                "customfield_10012": "AIR",
                "customfield_10020": "Yes",
                "customfield_10021": "<div>Noise</div>",
            },
        },
        {
            "source": "IVAS-2",
            "project": "IVAS",
            "issue_type": "Bug",
            "priority": "Medium",
            "fields": {
                "customfield_10012": "AIR",
                "customfield_10020": "No",
                "customfield_10021": "<div>Noise</div>",
            },
        },
    ]
    field_schema = {
        "customfield_10012": "team",
        "customfield_10020": "exist_on_production",
        "customfield_10021": "ops_notice_infobox",
    }

    template = build_import_template(issues, field_schema)

    assert template["common_fields"]["project"] == "IVAS"
    assert template["common_fields"]["priority"] == "Medium"
    assert template["common_fields"]["fields"]["team"] == "AIR"
    assert template["issue_type_fields"]["Bug"] == ["exist_on_production", "team"]

    candidate = next(
        item for item in template["candidate_fields"] if item["field"] == "exist_on_production"
    )
    assert candidate["classification"] == "type_specific_business"
    assert candidate["action"] == "review"
    review_item = next(item for item in template["review_queue"] if item["field"] == "exist_on_production")
    assert review_item["reason"] == "needs_human_confirmation"

    ignored = next(item for item in template["ignored_fields"] if item["field"] == "ops_notice_infobox")
    assert ignored["reason"] == "name_noise"


def test_import_engine_ignores_html_like_field_values() -> None:
    issues = [
        {
            "source": "IVAS-1",
            "project": "IVAS",
            "issue_type": "Task",
            "fields": {"customfield_10021": "<div>Noise</div>"},
        }
    ]

    template = build_import_template(issues, {"customfield_10021": "custom_business_field"})

    ignored = next(item for item in template["ignored_fields"] if item["field"] == "custom_business_field")
    assert ignored["reason"] == "html_value"


def test_import_engine_applies_confirmed_field_classifications() -> None:
    issues = [
        {
            "source": "IVAS-1",
            "project": "IVAS",
            "issue_type": "Bug",
            "fields": {
                "customfield_10020": "Yes",
                "customfield_10021": "Ignore me",
            },
        },
        {
            "source": "IVAS-2",
            "project": "IVAS",
            "issue_type": "Bug",
            "fields": {
                "customfield_10020": "No",
                "customfield_10021": "Ignore me",
            },
        },
    ]
    field_schema = {
        "customfield_10020": "exist_on_production",
        "customfield_10021": "ops_notice_infobox",
    }
    confirmed = {
        "exist_on_production": {
            "classification": "type_specific_business",
            "action": "keep",
            "confidence": 0.95,
            "suggested_for": ["Bug"],
            "reason": "Confirmed by reviewer",
        },
        "ops_notice_infobox": {
            "classification": "ui_noise",
            "action": "drop",
            "confidence": 0.99,
            "suggested_for": [],
            "reason": "Confirmed noise",
        },
    }

    template = build_import_template(issues, field_schema, confirmed_classifications=confirmed)

    assert template["candidate_fields"] == []
    assert template["review_queue"] == []
    confirmed_item = next(
        item for item in template["confirmed_fields"] if item["field"] == "exist_on_production"
    )
    assert confirmed_item["action"] == "keep"
    ignored = next(item for item in template["ignored_fields"] if item["field"] == "ops_notice_infobox")
    assert ignored["reason"] == "confirmed_drop"


def test_extract_aliases_from_field_schema() -> None:
    aliases = extract_aliases_from_field_schema(
        [
            {"id": "customfield_10012", "name": "Team", "custom": True},
            {"id": "summary", "name": "Summary", "custom": False},
        ]
    )

    assert aliases == {"team": "customfield_10012"}
