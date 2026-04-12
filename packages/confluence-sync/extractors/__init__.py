#!/usr/bin/env python3
"""
Confluence Extractors Package

Modules:
- markdown_extractor: Extract pages as Markdown with images
- images_extractor: Enhanced extractor with Draw.io support
- pdf_exporter: Export pages as PDF
- sync_state: Sync state for incremental updates

Configuration and client are now in cptools_confluence library.
"""

# Re-export from cptools_confluence for backwards compatibility
from cptools_confluence import (
    AuthConfig,
    ConfluenceClient,
    ExcludeConfig,
    SpaceConfig,
    SyncConfig,
    SyncSettings,
)

from .markdown_extractor import ConfluenceExtractor
from .sync_state import SyncStateManager

__all__ = [
    'ConfluenceClient',
    'ConfluenceExtractor',
    'SyncConfig',
    'ExcludeConfig',
    'SpaceConfig',
    'AuthConfig',
    'SyncSettings',
    'SyncStateManager',
]
