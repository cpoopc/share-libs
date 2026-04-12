#!/usr/bin/env python3
"""
Sync Configuration Module
Manages configuration for Confluence synchronization including:
- Connection settings
- Space configurations
- Exclusion rules
- Sync settings
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class SpaceConfig:
    """Configuration for a single Confluence space."""

    key: str
    output_dir: str
    flat: bool = False
    hierarchy_depth: int = 1  # 0=flat, 1=first-level, -1=full hierarchy


@dataclass
class ExcludeConfig:
    """Configuration for exclusion rules."""

    titles: List[str] = field(default_factory=list)
    labels: List[str] = field(default_factory=list)
    ancestors: List[str] = field(default_factory=list)

    def __post_init__(self):
        # Pre-compile title patterns for performance
        self._title_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.titles
        ]

    def should_exclude_by_title(self, title: str) -> bool:
        """Check if page should be excluded by title pattern."""
        for pattern in self._title_patterns:
            if pattern.search(title):
                return True
        return False

    def should_exclude_by_labels(self, page_labels: List[str]) -> bool:
        """Check if page should be excluded by labels."""
        page_labels_lower = [label.lower() for label in page_labels]
        for exclude_label in self.labels:
            if exclude_label.lower() in page_labels_lower:
                return True
        return False

    def should_exclude_by_ancestors(self, ancestor_titles: List[str]) -> bool:
        """Check if page should be excluded by ancestor titles."""
        for ancestor in ancestor_titles:
            if ancestor in self.ancestors:
                return True
        return False

    def should_exclude(self, page: Dict[str, Any]) -> tuple[bool, str]:
        """
        Check if a page should be excluded based on all rules.

        Returns:
            Tuple of (should_exclude, reason)
        """
        title = page.get("title", "")

        # Check title patterns
        if self.should_exclude_by_title(title):
            return True, "title matches exclusion pattern"

        # Check labels
        labels = page.get("metadata", {}).get("labels", {}).get("results", [])
        label_names = [label.get("name", "") for label in labels]
        if self.should_exclude_by_labels(label_names):
            return True, "has excluded label"

        # Check ancestors
        ancestors = page.get("ancestors", [])
        ancestor_titles = [a.get("title", "") for a in ancestors]
        if self.should_exclude_by_ancestors(ancestor_titles):
            return True, "under excluded ancestor"

        return False, ""


@dataclass
class SyncSettings:
    """Sync behavior settings."""

    incremental: bool = True
    state_file: str = ".sync_state.json"
    max_workers: int = 4
    download_images: bool = True
    dry_run: bool = False


@dataclass
class AuthConfig:
    """Authentication configuration."""

    username: str
    token: str
    use_bearer: bool = False


@dataclass
class SyncConfig:
    """Main configuration class for Confluence sync."""

    confluence_url: str
    auth: AuthConfig
    spaces: List[SpaceConfig]
    exclude: ExcludeConfig
    sync: SyncSettings

    @classmethod
    def _expand_env_vars(cls, value: Any) -> Any:
        """Recursively expand environment variables in config values."""
        if isinstance(value, str):
            # Match ${VAR} or $VAR patterns
            pattern = re.compile(r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)")

            def replace(match):
                var_name = match.group(1) or match.group(2)
                return os.environ.get(var_name, match.group(0))

            return pattern.sub(replace, value)
        elif isinstance(value, dict):
            return {k: cls._expand_env_vars(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [cls._expand_env_vars(item) for item in value]
        return value

    @classmethod
    def from_yaml(cls, path: str) -> "SyncConfig":
        """Load configuration from a YAML file."""
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)

        # Expand environment variables
        config = cls._expand_env_vars(raw_config)

        # Parse confluence section
        confluence = config.get("confluence", {})
        confluence_url = confluence.get("url", "")

        auth_config = confluence.get("auth", {})
        auth = AuthConfig(
            username=auth_config.get("username", ""),
            token=auth_config.get("token", ""),
            use_bearer=auth_config.get("use_bearer", False),
        )

        # Parse spaces
        spaces_config = config.get("spaces", [])
        spaces = [
            SpaceConfig(
                key=s.get("key", ""),
                output_dir=s.get("output_dir", "./output"),
                flat=s.get("flat", False),
                hierarchy_depth=s.get("hierarchy_depth", 1),  # Default: first-level
            )
            for s in spaces_config
        ]

        # Parse exclusion rules
        exclude_config = config.get("exclude", {})
        exclude = ExcludeConfig(
            titles=exclude_config.get("titles", []),
            labels=exclude_config.get("labels", []),
            ancestors=exclude_config.get("ancestors", []),
        )

        # Parse sync settings
        sync_config = config.get("sync", {})
        sync = SyncSettings(
            incremental=sync_config.get("incremental", True),
            state_file=sync_config.get("state_file", ".sync_state.json"),
            max_workers=sync_config.get("max_workers", 4),
            download_images=sync_config.get("download_images", True),
            dry_run=sync_config.get("dry_run", False),
        )

        return cls(
            confluence_url=confluence_url,
            auth=auth,
            spaces=spaces,
            exclude=exclude,
            sync=sync,
        )

    @classmethod
    def from_args(
        cls,
        url: str,
        username: str,
        token: str,
        space_key: str,
        output_dir: str,
        use_bearer: bool = False,
        flat: bool = False,
        incremental: bool = True,
        max_workers: int = 4,
        exclude_titles: Optional[List[str]] = None,
        exclude_labels: Optional[List[str]] = None,
        exclude_ancestors: Optional[List[str]] = None,
    ) -> "SyncConfig":
        """Create configuration from command-line arguments (backwards compatible)."""
        return cls(
            confluence_url=url,
            auth=AuthConfig(
                username=username,
                token=token,
                use_bearer=use_bearer,
            ),
            spaces=[
                SpaceConfig(
                    key=space_key,
                    output_dir=output_dir,
                    flat=flat,
                )
            ],
            exclude=ExcludeConfig(
                titles=exclude_titles or [],
                labels=exclude_labels or [],
                ancestors=exclude_ancestors or [],
            ),
            sync=SyncSettings(
                incremental=incremental,
                max_workers=max_workers,
            ),
        )

