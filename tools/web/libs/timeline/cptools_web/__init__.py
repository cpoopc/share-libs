"""
cptools-web: Web timeline visualization components for cp-tools

This package provides Python wrappers for timeline visualization components,
allowing easy integration with Python code without copying JS/CSS files.
"""

__version__ = "0.1.0"

from .timeline import TimelineRenderer
from .tree_timeline import TreeTimelineRenderer, create_trace_node

__all__ = [
    "TreeTimelineRenderer",
    "TimelineRenderer",
    "create_trace_node",
]
