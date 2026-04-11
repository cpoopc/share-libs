#!/usr/bin/env python3
"""
Kibana Log Searcher
Re-exports from cptools-kibana for backward compatibility.

注意: 通用的 Kibana 功能在 cptools-kibana 库中 (tools/python/libs/kibana)
"""

# Re-export from cptools-kibana
from cptools_kibana import LogSearcher

__all__ = ["LogSearcher"]
