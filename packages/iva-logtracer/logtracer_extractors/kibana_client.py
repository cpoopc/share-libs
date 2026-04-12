#!/usr/bin/env python3
"""
Kibana API Client
Re-exports from cptools-kibana for backward compatibility.

注意: 通用的 Kibana 功能在已安装的 `cptools-kibana` 包中
"""

# Re-export from cptools-kibana
from cptools_kibana import (
    KibanaClient,
    KibanaConfig,
    QueryBuilder,
    parse_time_range,
)

__all__ = ["KibanaClient", "KibanaConfig", "QueryBuilder", "parse_time_range"]
