#!/usr/bin/env python3
"""
Static cross-component correlation edges for iva-logtracer.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import yaml


@dataclass(frozen=True)
class CorrelationEdge:
    source_component: str
    source_field: str
    target_component: str
    target_field: str

    def render(self) -> str:
        return f"{self.source_component}.{self.source_field} -> {self.target_component}.{self.target_field}"


def get_correlation_graph_path() -> Path:
    """Return the YAML file that defines static correlation edges."""
    return Path(__file__).with_name("correlation_graph.yaml")


@lru_cache(maxsize=1)
def load_correlation_rows() -> tuple[dict[str, str], ...]:
    """Load raw correlation edges from YAML."""
    payload = yaml.safe_load(get_correlation_graph_path().read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("correlation_graph.yaml must contain a top-level list")

    rows: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("each correlation row in correlation_graph.yaml must be a mapping")
        required = {"source_component", "source_field", "target_component", "target_field"}
        missing = [key for key in required if not item.get(key)]
        if missing:
            raise ValueError(f"correlation_graph.yaml row missing required keys: {', '.join(sorted(missing))}")
        rows.append(
            {
                "source_component": str(item["source_component"]),
                "source_field": str(item["source_field"]),
                "target_component": str(item["target_component"]),
                "target_field": str(item["target_field"]),
            }
        )
    return tuple(rows)


@lru_cache(maxsize=1)
def _correlation_edges() -> tuple[CorrelationEdge, ...]:
    return tuple(CorrelationEdge(**row) for row in load_correlation_rows())


def get_incoming_edges(target_component: str) -> list[CorrelationEdge]:
    """Return direct incoming edges for the target component."""
    return [edge for edge in _correlation_edges() if edge.target_component == target_component]


@lru_cache(maxsize=1)
def _adjacency_map() -> dict[str, tuple[str, ...]]:
    adjacency: dict[str, list[str]] = {}
    for edge in _correlation_edges():
        adjacency.setdefault(edge.source_component, []).append(edge.target_component)
    return {component: tuple(targets) for component, targets in adjacency.items()}


def is_downstream_component(source_component: str, target_component: str) -> bool:
    """Return whether the target component is reachable from the source in the correlation graph."""
    if source_component == target_component:
        return False

    stack = list(_adjacency_map().get(source_component, ()))
    visited: set[str] = set()

    while stack:
        component = stack.pop()
        if component == target_component:
            return True
        if component in visited:
            continue
        visited.add(component)
        stack.extend(_adjacency_map().get(component, ()))

    return False
