from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
import yaml

from .models import ManifestFile, Profile, ResolvedTicket


def load_manifest(path: Path) -> ManifestFile:
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return ManifestFile(
        path=path,
        manifest=raw.get("manifest", {}),
        defaults=raw.get("defaults", {}),
        tickets=raw.get("tickets", []),
    )


def resolve_ticket(manifest: ManifestFile, profile: Profile, local_id: str) -> ResolvedTicket:
    ticket = next(ticket for ticket in manifest.tickets if ticket.get("local_id") == local_id)
    data = _deep_merge(profile.defaults, manifest.defaults)
    data = _deep_merge(data, ticket)
    return ResolvedTicket(data=data)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def update_ticket_in_manifest(path: Path, local_id: str, updates: dict[str, Any]) -> None:
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    for ticket in raw.get("tickets", []):
        if ticket.get("local_id") != local_id:
            continue
        for key, value in updates.items():
            ticket[key] = value
        break

    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(raw, handle, sort_keys=False, allow_unicode=False)
