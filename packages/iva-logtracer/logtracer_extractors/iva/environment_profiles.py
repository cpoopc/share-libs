#!/usr/bin/env python3
"""
Static environment routing profiles for iva-logtracer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from .component_catalog import iter_component_definitions


@dataclass(frozen=True)
class EnvironmentProfile:
    name: str
    aliases: list[str] = field(default_factory=list)
    default_backend: str = "primary"
    component_backends: dict[str, str] = field(default_factory=dict)


def get_environment_profiles_path() -> Path:
    return Path(__file__).with_name("environment_profiles.yaml")


@lru_cache(maxsize=1)
def load_environment_profile_rows() -> tuple[dict[str, object], ...]:
    payload = yaml.safe_load(get_environment_profiles_path().read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("environment_profiles.yaml must contain a top-level list")

    rows: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("each environment profile row must be a mapping")
        if not item.get("name"):
            raise ValueError("each environment profile row must have a name")
        rows.append(item)
    return tuple(rows)


@lru_cache(maxsize=1)
def _environment_profiles() -> tuple[EnvironmentProfile, ...]:
    supported_components = {definition.name for definition in iter_component_definitions()}
    profiles: list[EnvironmentProfile] = []

    for row in load_environment_profile_rows():
        component_backends = {
            str(component_name): str(backend_name)
            for component_name, backend_name in dict(row.get("component_backends", {})).items()
        }
        unknown_components = sorted(set(component_backends) - supported_components)
        if unknown_components:
            raise ValueError(
                "environment_profiles.yaml references unsupported components: "
                + ", ".join(unknown_components)
            )
        profiles.append(
            EnvironmentProfile(
                name=str(row["name"]),
                aliases=[str(alias) for alias in row.get("aliases", [])],
                default_backend=str(row.get("default_backend", "primary")),
                component_backends=component_backends,
            )
        )

    return tuple(profiles)


@lru_cache(maxsize=1)
def _profiles_by_alias() -> dict[str, EnvironmentProfile]:
    by_alias: dict[str, EnvironmentProfile] = {}
    for profile in _environment_profiles():
        by_alias[profile.name] = profile
        for alias in profile.aliases:
            by_alias[alias] = profile
    return by_alias


def get_environment_profile(name: str) -> EnvironmentProfile:
    key = name.strip().lower()
    try:
        return _profiles_by_alias()[key]
    except KeyError as exc:
        raise KeyError(f"Unknown environment profile: {name}") from exc
