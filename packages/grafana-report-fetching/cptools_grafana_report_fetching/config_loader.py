"""Config loader helpers for Grafana-backed report configs."""

from typing import Any

import yaml


def load_config(config_path: str) -> dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_dashboard_targets(config: dict[str, Any]) -> list[dict[str, Any]]:
    targets = []
    grafana_sources = config.get("grafana_sources", {})

    for key, value in config.items():
        if not isinstance(value, dict):
            continue

        uid = value.get("dashboard_uid")
        if not uid:
            continue

        source_key = value.get("source")
        source_config = grafana_sources.get(source_key, {})
        source_id = source_config.get("source_id", "")

        if any(t["uid"] == uid for t in targets):
            continue

        targets.append(
            {
                "name": f"{key.replace('_', ' ').title()} - {source_config.get('name', 'Unknown')}",
                "source_id": source_id,
                "uid": uid,
            }
        )

    return targets
