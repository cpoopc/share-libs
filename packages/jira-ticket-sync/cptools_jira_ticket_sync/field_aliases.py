from __future__ import annotations

from datetime import date, datetime
from typing import Any


def resolve_custom_fields(field_values: dict[str, Any], aliases: dict[str, str]) -> dict[str, Any]:
    return {aliases[name]: _normalize_field_value(value) for name, value in field_values.items()}


def _normalize_field_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_normalize_field_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_field_value(item) for key, item in value.items()}
    return value
