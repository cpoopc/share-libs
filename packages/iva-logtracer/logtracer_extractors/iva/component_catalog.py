#!/usr/bin/env python3
"""
IVA component catalog.

Defines the canonical component names used by the CLI and trace runtime.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from dataclasses import dataclass, field
from typing import Iterable
import yaml


@dataclass(frozen=True)
class ComponentDefinition:
    """Static metadata for a logical trace component."""

    name: str
    aliases: list[str] = field(default_factory=list)
    index_candidates: list[str] = field(default_factory=list)
    entry_fields: list[str] = field(default_factory=list)
    evidence_fields: list[str] = field(default_factory=list)
    default_enabled: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "aliases": list(self.aliases),
            "index_candidates": list(self.index_candidates),
            "entry_fields": list(self.entry_fields),
            "evidence_fields": list(self.evidence_fields),
            "default_enabled": self.default_enabled,
        }


def get_component_catalog_path() -> Path:
    """Return the YAML file that defines stable component metadata."""
    return Path(__file__).with_name("components.yaml")


@lru_cache(maxsize=1)
def load_component_catalog_rows() -> tuple[dict[str, object], ...]:
    """Load raw component metadata rows from YAML."""
    payload = yaml.safe_load(get_component_catalog_path().read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("components.yaml must contain a top-level list")

    rows: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("each component row in components.yaml must be a mapping")
        if not item.get("name"):
            raise ValueError("each component row in components.yaml must have a name")
        rows.append(item)
    return tuple(rows)


@lru_cache(maxsize=1)
def _component_definitions() -> tuple[ComponentDefinition, ...]:
    return tuple(
        ComponentDefinition(
            name=str(row["name"]),
            aliases=[str(alias) for alias in row.get("aliases", [])],
            index_candidates=[str(candidate) for candidate in row.get("index_candidates", [])],
            entry_fields=[str(field_name) for field_name in row.get("entry_fields", [])],
            evidence_fields=[str(field_name) for field_name in row.get("evidence_fields", [])],
            default_enabled=bool(row.get("default_enabled", True)),
        )
        for row in load_component_catalog_rows()
    )


@lru_cache(maxsize=1)
def _components_by_alias() -> dict[str, ComponentDefinition]:
    by_alias: dict[str, ComponentDefinition] = {}
    for definition in _component_definitions():
        by_alias[definition.name] = definition
        by_alias[definition.name.replace("_", "-")] = definition
        for alias in definition.aliases:
            by_alias[alias] = definition
    return by_alias


def iter_component_definitions() -> tuple[ComponentDefinition, ...]:
    """Return the canonical component definitions."""
    return _component_definitions()


def get_component_definition(name: str) -> ComponentDefinition:
    """Resolve a canonical component definition from a name or alias."""
    components_by_alias = _components_by_alias()
    try:
        return components_by_alias[name]
    except KeyError as exc:
        normalized = name.strip().lower().replace(" ", "_")
        normalized = normalized.replace("__", "_")
        if normalized in components_by_alias:
            return components_by_alias[normalized]
        hyphenated = normalized.replace("_", "-")
        if hyphenated in components_by_alias:
            return components_by_alias[hyphenated]
        raise KeyError(f"Unknown component: {name}") from exc


def resolve_component_names(names: Iterable[str]) -> list[str]:
    """Resolve component aliases to canonical names, preserving order."""
    resolved: list[str] = []
    seen: set[str] = set()

    for raw_name in names:
        definition = get_component_definition(raw_name)
        if definition.name in seen:
            continue
        resolved.append(definition.name)
        seen.add(definition.name)

    return resolved


def build_component_catalog_payload() -> list[dict[str, object]]:
    """Serialize the catalog for doctor/json output."""
    return [definition.to_dict() for definition in iter_component_definitions()]
