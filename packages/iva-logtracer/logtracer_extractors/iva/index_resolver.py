#!/usr/bin/env python3
"""
Resolve component index candidates against the current Kibana environment.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from .component_catalog import get_component_definition


@dataclass(frozen=True)
class IndexResolution:
    """Probe result for a single logical component."""

    component_name: str
    status: str
    index_candidates: list[str]
    resolved_indices: list[str]
    queryable_patterns: list[str] = field(default_factory=list)
    probe_hit_count: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status,
            "index_candidates": list(self.index_candidates),
            "resolved_indices": list(self.resolved_indices),
            "queryable_patterns": list(self.queryable_patterns),
            "probe_hit_count": self.probe_hit_count,
        }
        if self.error:
            payload["error"] = self.error
        return payload


@dataclass(frozen=True)
class PatternProbe:
    pattern: str
    resolved_indices: list[str]
    probe_hit_count: int


class IndexResolver:
    """Resolve logical components into currently available Elasticsearch indices."""

    def __init__(self, client: Any | None, *, probe: bool = True) -> None:
        self.client = client
        self.probe = probe and client is not None
        self._cache: dict[str, IndexResolution] = {}
        self._pattern_cache: dict[str, PatternProbe] = {}

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
                queryable_patterns=[],
            )
            self._cache[canonical_name] = resolution
            return resolution

        resolution = self._probe_definition(definition)
        self._cache[canonical_name] = resolution
        return resolution

    def prewarm_components(self, component_names: list[str], *, max_workers: int = 4) -> None:
        """Prime unique index-pattern probes for the given components in parallel."""
        if not self.probe or not component_names:
            return

        unique_patterns = list(
            dict.fromkeys(
                pattern
                for component_name in component_names
                for pattern in get_component_definition(component_name).index_candidates
            )
        )
        patterns_to_probe = [pattern for pattern in unique_patterns if pattern not in self._pattern_cache]
        if not patterns_to_probe:
            return

        worker_count = min(max_workers, len(patterns_to_probe))
        if worker_count <= 1:
            for pattern in patterns_to_probe:
                self._probe_pattern(pattern)
            return

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            list(executor.map(self._probe_pattern, patterns_to_probe))

    def _probe_definition(self, definition) -> IndexResolution:
        first_empty_resolution: IndexResolution | None = None
        for pattern in definition.index_candidates:
            try:
                probe = self._probe_pattern(pattern)
            except Exception as exc:
                return IndexResolution(
                    component_name=definition.name,
                    status=self._classify_error(exc),
                    index_candidates=list(definition.index_candidates),
                    resolved_indices=[],
                    queryable_patterns=[],
                    error=str(exc),
                )

            if not probe.resolved_indices:
                if probe.probe_hit_count > 0:
                    return IndexResolution(
                        component_name=definition.name,
                        status="matched",
                        index_candidates=list(definition.index_candidates),
                        resolved_indices=[],
                        queryable_patterns=[pattern],
                        probe_hit_count=probe.probe_hit_count,
                    )
                continue

            resolution = IndexResolution(
                component_name=definition.name,
                status="matched" if probe.probe_hit_count > 0 else "empty",
                index_candidates=list(definition.index_candidates),
                resolved_indices=probe.resolved_indices,
                queryable_patterns=[],
                probe_hit_count=probe.probe_hit_count,
            )
            if resolution.status == "matched":
                return resolution
            if first_empty_resolution is None:
                first_empty_resolution = resolution

        if first_empty_resolution is not None:
            return first_empty_resolution

        return IndexResolution(
            component_name=definition.name,
            status="empty",
            index_candidates=list(definition.index_candidates),
            resolved_indices=[],
            queryable_patterns=[],
            probe_hit_count=0,
        )

    def _probe_pattern(self, pattern: str) -> PatternProbe:
        cached = self._pattern_cache.get(pattern)
        if cached is not None:
            return cached

        result = self.client.search(
            query="*",
            index=pattern,
            size=1,
            source_includes=["@timestamp"],
            source_excludes=["*"],
            sort=[],
            track_total_hits=False,
            terminate_after=1,
        )
        hits = result.get("hits", {}).get("hits", [])
        if not isinstance(hits, list):
            hits = []

        resolved_indices: list[str] = []
        for hit in hits:
            if isinstance(hit, dict):
                index_name = hit.get("_index")
                if isinstance(index_name, str) and index_name and index_name not in resolved_indices:
                    resolved_indices.append(index_name)

        probe = PatternProbe(
            pattern=pattern,
            resolved_indices=resolved_indices,
            probe_hit_count=len(hits),
        )
        self._pattern_cache[pattern] = probe
        return probe

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        message = str(exc).lower()
        if any(token in message for token in ("401", "403", "unauthorized", "forbidden", "login failed")):
            return "auth_error"
        if any(token in message for token in ("connection error", "timed out", "timeout", "refused", "unreachable")):
            return "unreachable"
        return "unreachable"
