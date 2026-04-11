from __future__ import annotations

from pathlib import Path
from typing import Any
import json


def load_field_classifications(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        return {}

    fields = payload.get("fields", {})
    if not isinstance(fields, dict):
        return {}

    normalized: dict[str, dict[str, Any]] = {}
    for field_name, decision in fields.items():
        if not isinstance(field_name, str) or not isinstance(decision, dict):
            continue
        normalized[field_name] = {
            "classification": decision.get("classification", "uncertain"),
            "action": decision.get("action", "review"),
            "confidence": decision.get("confidence", 0.0),
            "suggested_for": decision.get("suggested_for", []),
            "reason": decision.get("reason", ""),
        }
    return normalized
