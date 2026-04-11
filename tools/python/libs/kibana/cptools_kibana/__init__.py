"""
cptools-kibana: Kibana/Elasticsearch client for cp-tools
"""

__version__ = "0.1.0"

from .client import KibanaClient, KibanaConfig
from .query import QueryBuilder, parse_time_range
from .searcher import LogSearcher

__all__ = [
    "KibanaClient",
    "KibanaConfig",
    "QueryBuilder",
    "parse_time_range",
    "LogSearcher",
]
