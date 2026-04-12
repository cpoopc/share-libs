#!/usr/bin/env python3
"""
Helpers for component-level diagnostics output.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable

from ..runtime import (
    get_component_probe_cache_path,
    get_component_probe_cache_ttl_seconds,
)
from .component_catalog import (
    build_component_catalog_payload,
    get_component_definition,
    iter_component_definitions,
    resolve_component_names,
)
from .index_resolver import IndexResolver

_COMPONENT_PROBE_CACHE_VERSION = 1


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_component_names(component_names: Iterable[str] | None = None) -> list[str]:
    if component_names is None:
        return [definition.name for definition in iter_component_definitions()]
    return resolve_component_names(component_names)


def _load_probe_cache(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"version": _COMPONENT_PROBE_CACHE_VERSION, "scopes": {}}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": _COMPONENT_PROBE_CACHE_VERSION, "scopes": {}}

    if not isinstance(payload, dict) or payload.get("version") != _COMPONENT_PROBE_CACHE_VERSION:
        return {"version": _COMPONENT_PROBE_CACHE_VERSION, "scopes": {}}

    scopes = payload.get("scopes")
    if not isinstance(scopes, dict):
        return {"version": _COMPONENT_PROBE_CACHE_VERSION, "scopes": {}}

    return {"version": _COMPONENT_PROBE_CACHE_VERSION, "scopes": scopes}


def _load_cached_component_payload(
    *,
    cache_path: Path,
    cache_scope: str,
    component_names: list[str],
    cache_ttl_seconds: int,
) -> list[dict[str, object]] | None:
    if cache_ttl_seconds <= 0:
        return None

    payload = _load_probe_cache(cache_path)
    scope_entry = payload.get("scopes", {}).get(cache_scope)
    if not isinstance(scope_entry, dict):
        return None

    cached_at_raw = scope_entry.get("cached_at")
    if not isinstance(cached_at_raw, str):
        return None

    try:
        cached_at = datetime.fromisoformat(cached_at_raw)
    except ValueError:
        return None

    if cached_at.tzinfo is None:
        cached_at = cached_at.replace(tzinfo=timezone.utc)

    age_seconds = (_utcnow() - cached_at).total_seconds()
    if age_seconds > cache_ttl_seconds:
        return None

    components = scope_entry.get("components")
    if not isinstance(components, dict):
        return None

    cached_entries: list[dict[str, object]] = []
    for component_name in component_names:
        entry = components.get(component_name)
        if not isinstance(entry, dict):
            return None
        cached_entries.append(entry)

    return cached_entries


def _write_cached_component_payload(
    *,
    cache_path: Path,
    cache_scope: str,
    payload: list[dict[str, object]],
    cache_ttl_seconds: int,
) -> None:
    cache_doc = _load_probe_cache(cache_path)
    scopes = cache_doc.setdefault("scopes", {})
    if not isinstance(scopes, dict):
        scopes = {}
        cache_doc["scopes"] = scopes

    scopes[cache_scope] = {
        "cached_at": _utcnow().isoformat(),
        "ttl_seconds": cache_ttl_seconds,
        "components": {
            str(entry["name"]): entry
            for entry in payload
            if isinstance(entry, dict) and entry.get("name")
        },
    }

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache_doc, indent=2, ensure_ascii=False), encoding="utf-8")


def build_component_diagnostics_map(
    client=None,
    component_names: Iterable[str] | None = None,
    *,
    probe: bool = True,
) -> dict[str, dict[str, object]]:
    """Build component diagnostics keyed by canonical component name."""
    resolver = IndexResolver(client, probe=probe)

    names = _resolve_component_names(component_names)

    if probe:
        resolver.prewarm_components(names)

    diagnostics: dict[str, dict[str, object]] = {}
    for component_name in names:
        definition = get_component_definition(component_name)
        resolution = resolver.resolve_component(component_name)
        entry = definition.to_dict()
        entry.update(resolution.to_dict())
        diagnostics[definition.name] = entry

    return diagnostics


def build_component_diagnostics_payload(
    client=None,
    component_names: Iterable[str] | None = None,
    *,
    probe: bool = True,
    cache_scope: str | None = None,
    cache_ttl_seconds: int | None = None,
) -> list[dict[str, object]]:
    """Build doctor/json-friendly component diagnostics payload."""
    if component_names is None and client is None and not probe:
        payload = build_component_catalog_payload()
        for entry in payload:
            entry.update(
                {
                    "status": "not_probed",
                    "resolved_indices": [],
                    "queryable_patterns": [],
                    "probe_hit_count": 0,
                }
            )
        return payload

    names = _resolve_component_names(component_names)
    ttl_seconds = get_component_probe_cache_ttl_seconds() if cache_ttl_seconds is None else cache_ttl_seconds
    cache_path = get_component_probe_cache_path()

    if probe and cache_scope:
        cached_payload = _load_cached_component_payload(
            cache_path=cache_path,
            cache_scope=cache_scope,
            component_names=names,
            cache_ttl_seconds=ttl_seconds,
        )
        if cached_payload is not None:
            return cached_payload

    payload = list(build_component_diagnostics_map(client, names, probe=probe).values())
    if probe and cache_scope:
        _write_cached_component_payload(
            cache_path=cache_path,
            cache_scope=cache_scope,
            payload=payload,
            cache_ttl_seconds=ttl_seconds,
        )
    return payload
