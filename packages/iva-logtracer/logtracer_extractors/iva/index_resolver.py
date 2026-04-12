#!/usr/bin/env python3
"""
Resolve component index candidates against the current Kibana environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .component_catalog import get_component_definition


@dataclass(frozen=True)
class IndexResolution:
    """Probe result for a single logical component."""

    component_name: str
    status: str
    index_candidates: list[str]
    resolved_indices: list[str]
    document_count: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status,
            "index_candidates": list(self.index_candidates),
            "resolved_indices": list(self.resolved_indices),
            "document_count": self.document_count,
        }
        if self.error:
            payload["error"] = self.error
        return payload


class IndexResolver:
    """Resolve logical components into currently available Elasticsearch indices."""

    def __init__(self, client: Any | None, *, probe: bool = True) -> None:
        self.client = client
        self.probe = probe and client is not None
        self._cache: dict[str, IndexResolution] = {}

    def resolve_component(self, component_name: str) -> IndexResolution:
        canonical_name = get_component_definition(component_name).name
        cached = self._cache.get(canonical_name)
        if cached is not None:
            return cached

        definition = get_component_definition(canonical_name)
        if not self.probe:
            resolution = IndexResolution(
                component_name=definition.name,
                status="not_probed",
                index_candidates=list(definition.index_candidates),
                resolved_indices=[],
            )
            self._cache[canonical_name] = resolution
            return resolution

        resolution = self._probe_definition(definition)
        self._cache[canonical_name] = resolution
        return resolution

    def _probe_definition(self, definition) -> IndexResolution:
        for pattern in definition.index_candidates:
            try:
                resolved = self.client.resolve_indices(pattern)
                resolved_indices = list(resolved.get("indices", []))
            except Exception as exc:
                return IndexResolution(
                    component_name=definition.name,
                    status=self._classify_error(exc),
                    index_candidates=list(definition.index_candidates),
                    resolved_indices=[],
                    error=str(exc),
                )

            if not resolved_indices:
                continue

            try:
                document_count = int(self.client.count(query="*", index=pattern))
            except Exception as exc:
                return IndexResolution(
                    component_name=definition.name,
                    status=self._classify_error(exc),
                    index_candidates=list(definition.index_candidates),
                    resolved_indices=resolved_indices,
                    error=str(exc),
                )

            return IndexResolution(
                component_name=definition.name,
                status="matched" if document_count > 0 else "empty",
                index_candidates=list(definition.index_candidates),
                resolved_indices=resolved_indices,
                document_count=document_count,
            )

        return IndexResolution(
            component_name=definition.name,
            status="empty",
            index_candidates=list(definition.index_candidates),
            resolved_indices=[],
            document_count=0,
        )

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        message = str(exc).lower()
        if any(token in message for token in ("401", "403", "unauthorized", "forbidden", "login failed")):
            return "auth_error"
        if any(token in message for token in ("connection error", "timed out", "timeout", "refused", "unreachable")):
            return "unreachable"
        return "unreachable"
