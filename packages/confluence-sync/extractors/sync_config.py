#!/usr/bin/env python3
"""
Sync Configuration Module - DEPRECATED

This module is deprecated. Please import from cptools_confluence instead:

    from cptools_confluence import SyncConfig, ExcludeConfig, SpaceConfig, AuthConfig, SyncSettings

This file is kept for backward compatibility only.
"""

# Re-export from cptools_confluence for backward compatibility
from cptools_confluence import (
    AuthConfig,
    ExcludeConfig,
    SpaceConfig,
    SyncConfig,
    SyncSettings,
)

__all__ = [
    "AuthConfig",
    "ExcludeConfig",
    "SpaceConfig",
    "SyncConfig",
    "SyncSettings",
]
