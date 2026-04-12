from __future__ import annotations

from typing import Any

from cptools_grafana import GrafanaClient, GrafanaConfig

from .runtime import materialize_source_env


def get_grafana_client(source_config: dict[str, Any]) -> GrafanaClient:
    source_id = source_config.get("source_id", "")
    materialize_source_env(source_id)
    return GrafanaClient.from_env(source_id)


__all__ = ["get_grafana_client", "GrafanaClient", "GrafanaConfig"]
