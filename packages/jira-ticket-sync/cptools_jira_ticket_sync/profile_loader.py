from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import Profile


def load_profile(path: Path) -> Profile:
    raw = _load_yaml(path)
    profile_data = raw.get("profile", {})
    return Profile(
        id=profile_data["id"],
        project=profile_data["project"],
        defaults=profile_data.get("defaults", {}),
        managed_fields=profile_data.get("managed_fields", []),
        field_aliases=profile_data.get("field_aliases", {}),
        required_fields=profile_data.get("required_fields", []),
        validation=profile_data.get("validation", {}),
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def update_profile_field_aliases(path: Path, aliases: dict[str, str]) -> None:
    raw = _load_yaml(path)
    profile_data = raw.setdefault("profile", {})
    current = profile_data.setdefault("field_aliases", {})
    current.update(aliases)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(raw, handle, sort_keys=False, allow_unicode=False)
