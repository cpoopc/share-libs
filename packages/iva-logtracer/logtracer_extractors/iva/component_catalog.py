#!/usr/bin/env python3
"""
IVA component catalog.

Defines the canonical component names used by the CLI and trace runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


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


_COMPONENT_DEFINITIONS = (
    ComponentDefinition(
        name="assistant_runtime",
        aliases=["assistant-runtime", "air", "assistant runtime", "runtime"],
        index_candidates=["*:*-logs-air_assistant_runtime-*"],
        entry_fields=["sessionId", "conversationId", "accountId"],
        evidence_fields=["message", "sessionId", "conversationId", "accountId"],
    ),
    ComponentDefinition(
        name="agent_service",
        aliases=["agent-service", "agent service"],
        index_candidates=["*:*-logs-air_agent_service-*"],
        entry_fields=["conversationId"],
        evidence_fields=["message", "conversationId"],
    ),
    ComponentDefinition(
        name="nca",
        aliases=["nova-conversation-adapter"],
        index_candidates=["*:*-logs-nca-*"],
        entry_fields=["conversation_id"],
        evidence_fields=["message", "conversation_id", "request_id"],
    ),
    ComponentDefinition(
        name="aig",
        aliases=[],
        index_candidates=["*:*-logs-aig-*"],
        entry_fields=["request_id"],
        evidence_fields=["message", "request_id"],
    ),
    ComponentDefinition(
        name="gmg",
        aliases=[],
        index_candidates=["*:*-logs-gmg-*"],
        entry_fields=["log_context_RCRequestId"],
        evidence_fields=["message", "log_context_RCRequestId"],
    ),
    ComponentDefinition(
        name="cprc_srs",
        aliases=["cprc-srs", "srs"],
        index_candidates=["*:*-ai-cprc*"],
        entry_fields=["message"],
        evidence_fields=["message"],
    ),
    ComponentDefinition(
        name="cprc_sgs",
        aliases=["cprc-sgs", "sgs"],
        index_candidates=["*:*-ai-cprc*"],
        entry_fields=["message"],
        evidence_fields=["message"],
    ),
)

_COMPONENTS_BY_ALIAS: dict[str, ComponentDefinition] = {}
for definition in _COMPONENT_DEFINITIONS:
    _COMPONENTS_BY_ALIAS[definition.name] = definition
    _COMPONENTS_BY_ALIAS[definition.name.replace("_", "-")] = definition
    for alias in definition.aliases:
        _COMPONENTS_BY_ALIAS[alias] = definition


def iter_component_definitions() -> tuple[ComponentDefinition, ...]:
    """Return the canonical component definitions."""
    return _COMPONENT_DEFINITIONS


def get_component_definition(name: str) -> ComponentDefinition:
    """Resolve a canonical component definition from a name or alias."""
    try:
        return _COMPONENTS_BY_ALIAS[name]
    except KeyError as exc:
        normalized = name.strip().lower().replace(" ", "_")
        normalized = normalized.replace("__", "_")
        if normalized in _COMPONENTS_BY_ALIAS:
            return _COMPONENTS_BY_ALIAS[normalized]
        hyphenated = normalized.replace("_", "-")
        if hyphenated in _COMPONENTS_BY_ALIAS:
            return _COMPONENTS_BY_ALIAS[hyphenated]
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
