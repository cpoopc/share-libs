"""
cptools-confluence: Confluence API client and utilities for cp-tools.

Main components:
- ConfluenceClient: Unified Confluence API client wrapper
- SyncConfig: Configuration management for Confluence sync operations
- get_client_from_env: Factory to create client from environment variables

Quick Start:
    # Auto-load .env and create client
    from cptools_confluence import get_client_from_env
    client = get_client_from_env()

    # Or manually create client
    from cptools_confluence import ConfluenceClient
    client = ConfluenceClient(
        base_url="https://wiki.example.com",
        username="user@example.com",
        api_token="your-token",
    )
"""

from .client import ConfluenceClient
from .config import (
    AuthConfig,
    ExcludeConfig,
    SpaceConfig,
    SyncConfig,
    SyncSettings,
)
from .env import (
    get_client_from_env,
    get_confluence_defaults,
    load_confluence_env,
)

__all__ = [
    # Client
    "ConfluenceClient",
    # Factory functions
    "get_client_from_env",
    "get_confluence_defaults",
    "load_confluence_env",
    # Config classes
    "AuthConfig",
    "ExcludeConfig",
    "SpaceConfig",
    "SyncConfig",
    "SyncSettings",
]
