#!/usr/bin/env python3
"""
Helpers for component-level diagnostics output.
"""

from __future__ import annotations

from typing import Iterable

from .component_catalog import (
    build_component_catalog_payload,
    get_component_definition,
    iter_component_definitions,
    resolve_component_names,
)
from .index_resolver import IndexResolver


def build_component_diagnostics_map(
    client=None,
    component_names: Iterable[str] | None = None,
    *,
    probe: bool = True,
) -> dict[str, dict[str, object]]:
    """Build component diagnostics keyed by canonical component name."""
    resolver = IndexResolver(client, probe=probe)

    if component_names is None:
        names = [definition.name for definition in iter_component_definitions()]
    else:
        names = resolve_component_names(component_names)

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
) -> list[dict[str, object]]:
    """Build doctor/json-friendly component diagnostics payload."""
    if component_names is None and client is None and not probe:
        payload = build_component_catalog_payload()
        for entry in payload:
            entry.update(
                {
                    "status": "not_probed",
                    "resolved_indices": [],
                    "document_count": 0,
                }
            )
        return payload

    return list(build_component_diagnostics_map(client, component_names, probe=probe).values())
