from __future__ import annotations

from pathlib import Path

from cptools_jira_ticket_sync.field_classification_store import load_field_classifications


def test_load_field_classifications_reads_valid_fields(tmp_path: Path) -> None:
    path = tmp_path / "IVAS.json"
    path.write_text(
        """{
  "project": "IVAS",
  "fields": {
    "exist_on_production": {
      "classification": "type_specific_business",
      "action": "keep",
      "confidence": 0.91,
      "suggested_for": ["Bug"],
      "reason": "Bug impact indicator"
    }
  }
}""",
        encoding="utf-8",
    )

    data = load_field_classifications(path)

    assert data["exist_on_production"]["classification"] == "type_specific_business"
    assert data["exist_on_production"]["action"] == "keep"


def test_load_field_classifications_returns_empty_for_missing_file(tmp_path: Path) -> None:
    data = load_field_classifications(tmp_path / "missing.json")
    assert data == {}
