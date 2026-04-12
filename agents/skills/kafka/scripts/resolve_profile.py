#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

import yaml


def deep_merge(base: object, override: object) -> object:
    if isinstance(base, dict) and isinstance(override, dict):
        merged = {key: deepcopy(value) for key, value in base.items()}
        for key, value in override.items():
            if key in merged:
                merged[key] = deep_merge(merged[key], value)
            else:
                merged[key] = deepcopy(value)
        return merged
    return deepcopy(override)


def load_profiles() -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    config_path = Path(__file__).resolve().parent.parent / "references" / "environment-profiles.yaml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    shared_defaults = data.get("shared_defaults", {})
    profiles = data.get("profiles", {})
    return shared_defaults, profiles


def build_alias_index(profiles: dict[str, dict[str, object]]) -> dict[str, str]:
    alias_index: dict[str, str] = {}
    for canonical_name, profile in profiles.items():
        candidates = [canonical_name, *profile.get("aliases", [])]
        for candidate in candidates:
            normalized = str(candidate).strip().lower()
            if normalized in alias_index and alias_index[normalized] != canonical_name:
                raise ValueError(f"duplicate alias '{candidate}' for {canonical_name} and {alias_index[normalized]}")
            alias_index[normalized] = canonical_name
    return alias_index


def resolve_profile(requested: str, shared_defaults: dict[str, object], profiles: dict[str, dict[str, object]]) -> dict[str, object]:
    alias_index = build_alias_index(profiles)
    normalized = requested.strip().lower()
    if normalized not in alias_index:
        known = ", ".join(sorted(profiles))
        raise KeyError(f"unknown profile or alias '{requested}'. Known profiles: {known}")

    canonical_name = alias_index[normalized]
    resolved = deep_merge(shared_defaults, profiles[canonical_name])
    resolved["canonical_profile"] = canonical_name
    resolved["requested"] = requested
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve IVA Kafka environment profiles and aliases.")
    parser.add_argument("profile", nargs="?", help="Canonical profile or alias to resolve.")
    parser.add_argument("--format", choices=("json", "yaml"), default="json", help="Output format.")
    parser.add_argument("--list", action="store_true", help="List canonical profiles and aliases.")
    return parser.parse_args()


def print_profile_list(profiles: dict[str, dict[str, object]]) -> int:
    for canonical_name in sorted(profiles):
        aliases = ", ".join(profiles[canonical_name].get("aliases", []))
        print(f"{canonical_name}: {aliases}")
    return 0


def main() -> int:
    args = parse_args()
    shared_defaults, profiles = load_profiles()

    if args.list:
        return print_profile_list(profiles)

    if not args.profile:
        print("error: profile is required unless --list is used", file=sys.stderr)
        return 2

    try:
        resolved = resolve_profile(args.profile, shared_defaults, profiles)
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.format == "yaml":
        print(yaml.safe_dump(resolved, sort_keys=False).strip())
    else:
        print(json.dumps(resolved, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
