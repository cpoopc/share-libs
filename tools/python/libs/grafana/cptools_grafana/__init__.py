"""
cptools-grafana: Grafana client for cp-tools
"""

__version__ = "0.1.0"

from .client import GrafanaClient, GrafanaConfig

__all__ = [
    "GrafanaClient",
    "GrafanaConfig",
]

