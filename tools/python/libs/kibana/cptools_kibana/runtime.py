from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import dotenv_values, load_dotenv


APP_NAME = "kibana-query"
DEFAULT_ENV_TEMPLATE = """# Kibana / Elasticsearch credentials
KIBANA_URL=https://kibana.example.com
KIBANA_USERNAME=your-username
KIBANA_PASSWORD=your-password

# Optional
KIBANA_INDEX=*:*-logs-*
KIBANA_VERIFY_CERTS=true
KIBANA_TIMEOUT=30
"""


@dataclass(frozen=True)
class RuntimePaths:
    config_root: Path
    cache_root: Path
    env_file: Path


def get_config_root() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME


def get_cache_root() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / APP_NAME


def resolve_env_file(env_name: str | None = None) -> Path:
    config_root = get_config_root()
    if env_name:
        return config_root / f".env.{env_name}"
    return config_root / ".env"


def ensure_layout(force: bool = False) -> dict[str, Any]:
    config_root = get_config_root()
    cache_root = get_cache_root()
    config_root.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    for path in (
        config_root / ".env",
        config_root / ".env.example",
        config_root / ".env.lab",
        config_root / ".env.production",
    ):
        if force or not path.exists():
            path.write_text(DEFAULT_ENV_TEMPLATE, encoding="utf-8")
            created.append(str(path))

    return {
        "config_root": str(config_root),
        "cache_root": str(cache_root),
        "created": created,
    }


def load_runtime_env(env_name: str | None = None, env_file: str | None = None) -> RuntimePaths:
    config_root = get_config_root()
    cache_root = get_cache_root()
    cache_root.mkdir(parents=True, exist_ok=True)
    config_root.mkdir(parents=True, exist_ok=True)

    selected_env_file = Path(env_file).expanduser() if env_file else resolve_env_file(env_name)
    if selected_env_file.exists():
        load_dotenv(selected_env_file, override=True)

    return RuntimePaths(
        config_root=config_root,
        cache_root=cache_root,
        env_file=selected_env_file,
    )


def doctor(env_name: str | None = None, env_file: str | None = None) -> dict[str, Any]:
    paths = load_runtime_env(env_name=env_name, env_file=env_file)
    env_values = dotenv_values(paths.env_file) if paths.env_file.exists() else {}

    url_value = env_values.get("KIBANA_URL") or env_values.get("KIBANA_ES_URL") or os.getenv("KIBANA_URL") or os.getenv("KIBANA_ES_URL")
    username_value = env_values.get("KIBANA_USERNAME") or os.getenv("KIBANA_USERNAME")
    password_value = env_values.get("KIBANA_PASSWORD") or os.getenv("KIBANA_PASSWORD")

    checks = {
        "env_file_exists": paths.env_file.exists(),
        "kibana_url": bool(url_value),
        "kibana_username": bool(username_value),
        "kibana_password": bool(password_value),
    }
    ok = all(checks.values())

    return {
        "app_name": APP_NAME,
        "config_root": str(paths.config_root),
        "cache_root": str(paths.cache_root),
        "env_file": str(paths.env_file),
        "selected_env": env_name or "default",
        "checks": checks,
        "ok": ok,
    }
