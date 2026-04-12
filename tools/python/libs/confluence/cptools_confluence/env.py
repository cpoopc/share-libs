#!/usr/bin/env python3
"""
Environment and factory utilities for Confluence client.

Provides convenient functions to create ConfluenceClient from environment variables
with automatic .env file loading.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from cptools_common.config import get_env, get_project_root, load_dotenv

from .client import ConfluenceClient
from .config import SyncConfig

# Default environment variable names
ENV_CONFLUENCE_URL = "CONFLUENCE_URL"
ENV_CONFLUENCE_USERNAME = "CONFLUENCE_USERNAME"
ENV_CONFLUENCE_TOKEN = "CONFLUENCE_TOKEN"
ENV_CONFLUENCE_USE_BEARER = "CONFLUENCE_USE_BEARER"


@dataclass(frozen=True)
class ConfluenceDefaults:
    """Resolved Confluence connection defaults from config and environment."""

    url: str = ""
    use_bearer: bool = False


def load_confluence_env(
    *extra_paths: Union[str, Path],
    include_project_root: bool = True,
    include_cwd: bool = True,
) -> List[Path]:
    """
    Load .env files for Confluence configuration.

    Automatically looks for .env files in common locations:
    1. Project root directory (if include_project_root=True)
    2. Current working directory (if include_cwd=True)
    3. Any additional paths provided

    Priority (later files override earlier):
    project_root/.env < cwd/.env < extra_paths (in order)

    Args:
        *extra_paths: Additional .env file paths to load
        include_project_root: Include project root .env (default: True)
        include_cwd: Include current directory .env (default: True)

    Returns:
        List of paths that were successfully loaded

    Example:
        >>> load_confluence_env()
        >>> load_confluence_env(Path(__file__).parent / '.env')
    """
    paths_to_load = []

    # Add project root .env (lowest priority)
    if include_project_root:
        try:
            project_root = get_project_root()
            paths_to_load.append(project_root / ".env")
        except Exception:
            pass

    # Add cwd .env
    if include_cwd:
        cwd_env = Path.cwd() / ".env"
        if cwd_env not in paths_to_load:
            paths_to_load.append(cwd_env)

    # Add extra paths (highest priority)
    for path in extra_paths:
        paths_to_load.append(Path(path))

    return load_dotenv(*paths_to_load)


def _candidate_config_paths() -> List[Path]:
    """Return likely config.yaml locations ordered from nearest to broadest."""
    candidates: List[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            candidates.append(path)

    cwd = Path.cwd()
    add(cwd / "config.yaml")
    add(cwd / "apps" / "confluence" / "config.yaml")

    try:
        project_root = get_project_root()
        add(project_root / "config.yaml")
        add(project_root / "apps" / "confluence" / "config.yaml")
    except Exception:
        pass

    return candidates


def _load_defaults_from_config() -> ConfluenceDefaults:
    """Load URL and auth defaults from the first available config.yaml."""
    for config_path in _candidate_config_paths():
        if not config_path.exists():
            continue

        config = SyncConfig.from_yaml(str(config_path))
        return ConfluenceDefaults(
            url=config.confluence_url,
            use_bearer=config.auth.use_bearer,
        )

    return ConfluenceDefaults()


def get_confluence_defaults(
    load_env: bool = True,
    env_paths: Optional[List[Union[str, Path]]] = None,
) -> ConfluenceDefaults:
    """
    Resolve Confluence URL and auth defaults from env first, then config.yaml.

    This allows app-level config.yaml to provide stable defaults for URL and
    bearer-token auth while preserving env override semantics.
    """
    if load_env:
        extra_paths = env_paths or []
        load_confluence_env(*extra_paths)

    config_defaults = _load_defaults_from_config()
    url = get_env(ENV_CONFLUENCE_URL, default=config_defaults.url)
    use_bearer_str = get_env(
        ENV_CONFLUENCE_USE_BEARER,
        default="true" if config_defaults.use_bearer else "false",
    )

    return ConfluenceDefaults(
        url=url,
        use_bearer=use_bearer_str.lower() in ("true", "1", "yes"),
    )


def get_client_from_env(
    url: Optional[str] = None,
    username: Optional[str] = None,
    token: Optional[str] = None,
    use_bearer: Optional[bool] = None,
    load_env: bool = True,
    env_paths: Optional[List[Union[str, Path]]] = None,
) -> ConfluenceClient:
    """
    Create a ConfluenceClient from environment variables.

    Optionally loads .env files before reading environment variables.

    Args:
        url: Confluence URL (overrides env var)
        username: Username (overrides env var)
        token: API token (overrides env var)
        use_bearer: Use bearer token auth (overrides env var)
        load_env: Whether to load .env files (default: True)
        env_paths: Additional .env paths to load

    Returns:
        Configured ConfluenceClient

    Raises:
        ValueError: If required configuration is missing

    Environment Variables:
        CONFLUENCE_URL: Base URL (e.g., https://wiki.example.com)
        CONFLUENCE_USERNAME: Username/email
        CONFLUENCE_TOKEN: API token or password
        CONFLUENCE_USE_BEARER: "true" to use bearer token auth

    Example:
        >>> # Auto-load .env and create client
        >>> client = get_client_from_env()
        >>>
        >>> # Override URL but use env for credentials
        >>> client = get_client_from_env(url="https://wiki.mycompany.com")
        >>>
        >>> # Skip .env loading (use system env only)
        >>> client = get_client_from_env(load_env=False)
    """
    defaults = get_confluence_defaults(load_env=load_env, env_paths=env_paths)

    # Get configuration from env or parameters
    final_url = url or defaults.url
    final_username = username or get_env(ENV_CONFLUENCE_USERNAME, default="")
    final_token = token or get_env(ENV_CONFLUENCE_TOKEN)

    # Parse use_bearer from env if not provided
    if use_bearer is None:
        final_use_bearer = defaults.use_bearer
    else:
        final_use_bearer = use_bearer

    # Validate required fields
    if not final_url:
        raise ValueError(
            f"Confluence URL is required. "
            f"Set {ENV_CONFLUENCE_URL} environment variable or pass url parameter."
        )
    if not final_token:
        raise ValueError(
            f"Confluence token is required. "
            f"Set {ENV_CONFLUENCE_TOKEN} environment variable or pass token parameter."
        )

    return ConfluenceClient(
        base_url=final_url,
        username=final_username,
        api_token=final_token,
        use_bearer_token=final_use_bearer,
    )
