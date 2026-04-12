from __future__ import annotations

import os
import shutil
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from cptools_common.config import load_dotenv
from cptools_grafana import GrafanaClient


APP_NAME = "grafana-report-fetching"
PLACEHOLDER_VALUES = {
    "GRAFANA_URL": {"https://grafana.example.com", "https://example.com"},
    "GRAFANA_API_KEY": {"replace-with-api-key", "changeme", "your-api-key"},
    "GRAFANA_IVA_URL": {"https://grafana.example.com", "https://example.com"},
    "GRAFANA_IVA_API_KEY": {"replace-with-api-key", "changeme", "your-api-key"},
    "GRAFANA_RC_URL": {"https://grafana.example.com", "https://example.com"},
    "GRAFANA_RC_API_KEY": {"replace-with-api-key", "changeme", "your-api-key"},
    "GRAFANA_RC_USERNAME": {"your-username", "user@example.com"},
    "GRAFANA_RC_PASSWORD": {"your-password", "changeme"},
}


def _asset_path(name: str) -> Path:
    return Path(resources.files("cptools_grafana_report_fetching").joinpath("assets", name))


def _xdg_dir(env_var: str, fallback_suffix: str) -> Path:
    override = os.getenv(env_var)
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / fallback_suffix).resolve()


def get_config_root() -> Path:
    override = os.getenv("GRAFANA_REPORT_FETCHING_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return _xdg_dir("XDG_CONFIG_HOME", ".config") / APP_NAME


def get_cache_root() -> Path:
    override = os.getenv("GRAFANA_REPORT_FETCHING_CACHE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return _xdg_dir("XDG_CACHE_HOME", ".cache") / APP_NAME


def get_output_root() -> Path:
    override = os.getenv("GRAFANA_REPORT_FETCHING_OUTPUT_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return get_cache_root() / "output"


def get_default_env_path(env_name: str | None = None) -> Path:
    suffix = f".{env_name}" if env_name else ""
    return get_config_root() / f".env{suffix}"


def resolve_profile_file(profile_file: str | os.PathLike[str] | None = None) -> Path:
    if profile_file:
        return Path(profile_file).expanduser().resolve()
    config_candidate = get_config_root() / "profile-aliases.yaml"
    if config_candidate.exists():
        return config_candidate
    return _asset_path("profile-aliases.yaml")


def resolve_core_metrics_config(config_file: str | os.PathLike[str] | None = None) -> Path:
    if config_file:
        return Path(config_file).expanduser().resolve()
    config_candidate = get_config_root() / "core-metrics-daily.yaml"
    if config_candidate.exists():
        return config_candidate
    return _asset_path("core-metrics-daily.yaml")


def ensure_layout(force: bool = False) -> dict[str, Any]:
    config_root = get_config_root()
    cache_root = get_cache_root()
    output_root = get_output_root()
    config_root.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    assets = {
        config_root / ".env.example": _asset_path(".env.example"),
        config_root / ".env": _asset_path(".env.example"),
        config_root / ".env.lab": _asset_path(".env.example"),
        config_root / ".env.production": _asset_path(".env.example"),
        config_root / "profile-aliases.yaml": _asset_path("profile-aliases.yaml"),
        config_root / "core-metrics-daily.yaml": _asset_path("core-metrics-daily.yaml"),
    }
    for destination, source in assets.items():
        if force or not destination.exists():
            destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            created.append(str(destination))

    return {
        "config_root": str(config_root),
        "cache_root": str(cache_root),
        "output_root": str(output_root),
        "created": created,
    }


def load_runtime_env(env_name: str | None = None, env_file: str | None = None) -> dict[str, Path]:
    ensure_layout(force=False)
    selected_env = Path(env_file).expanduser().resolve() if env_file else get_default_env_path(env_name)
    load_dotenv(selected_env, override=True)
    return {
        "config_root": get_config_root(),
        "cache_root": get_cache_root(),
        "output_root": get_output_root(),
        "env_file": selected_env,
        "profile_file": resolve_profile_file(),
        "core_metrics_config": resolve_core_metrics_config(),
    }


def load_profile_aliases(profile_file: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    path = resolve_profile_file(profile_file)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def resolve_profile(requested: str | None, profile_file: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    data = load_profile_aliases(profile_file)
    profiles = data.get("profiles", {})
    normalized = (requested or "default").strip().lower()
    for profile_name, profile in profiles.items():
        aliases = {profile_name.lower(), *(alias.lower() for alias in profile.get("aliases", []))}
        if normalized in aliases:
            resolved = dict(profile)
            resolved["profile_name"] = profile_name
            resolved["requested"] = requested or profile_name
            return resolved
    raise ValueError(f"Unknown Grafana profile or alias: {requested}")


def resolve_profile_for_source_id(
    source_id: str | None,
    profile_file: str | os.PathLike[str] | None = None,
) -> dict[str, Any] | None:
    normalized_source_id = (source_id or "").upper()
    data = load_profile_aliases(profile_file)
    for profile_name, profile in data.get("profiles", {}).items():
        if str(profile.get("canonical_source_id", "")).upper() == normalized_source_id:
            resolved = dict(profile)
            resolved["profile_name"] = profile_name
            resolved["requested"] = profile_name
            return resolved
    return None


def _default_env_mapping() -> dict[str, str]:
    return {
        "url": "GRAFANA_URL",
        "api_key": "GRAFANA_API_KEY",
        "username": "GRAFANA_USERNAME",
        "password": "GRAFANA_PASSWORD",
    }


def materialize_profile_env(profile: dict[str, Any]) -> None:
    env_map = profile.get("env", {})
    if not profile.get("fallback_to_default_env"):
        return
    for key, default_var in _default_env_mapping().items():
        target_var = env_map.get(key)
        if target_var and not os.environ.get(target_var) and os.environ.get(default_var):
            os.environ[target_var] = os.environ[default_var]


def materialize_source_env(
    source_id: str | None,
    profile_file: str | os.PathLike[str] | None = None,
) -> None:
    profile = resolve_profile_for_source_id(source_id, profile_file)
    if profile:
        materialize_profile_env(profile)


def profile_env_status(profile: dict[str, Any]) -> dict[str, Any]:
    env_map = profile.get("env", {})
    url_var = env_map.get("url")
    api_key_var = env_map.get("api_key")
    username_var = env_map.get("username")
    password_var = env_map.get("password")

    status = {
        "url_var": url_var,
        "api_key_var": api_key_var,
        "username_var": username_var,
        "password_var": password_var,
        "url_present": bool(url_var and os.environ.get(url_var)),
        "api_key_present": bool(api_key_var and os.environ.get(api_key_var)),
        "username_present": bool(username_var and os.environ.get(username_var)),
        "password_present": bool(password_var and os.environ.get(password_var)),
    }
    status["auth_ok"] = status["api_key_present"] or (
        status["username_present"] and status["password_present"]
    )
    return status


def placeholder_env_vars() -> list[str]:
    present_placeholders: list[str] = []
    for key, values in PLACEHOLDER_VALUES.items():
        value = os.environ.get(key)
        if value and value in values:
            present_placeholders.append(key)
    return present_placeholders


def doctor(
    *,
    env_name: str | None = None,
    env_file: str | None = None,
    profile_name: str | None = None,
    profile_file: str | os.PathLike[str] | None = None,
    real: bool = False,
) -> dict[str, Any]:
    paths = load_runtime_env(env_name=env_name, env_file=env_file)
    profile = resolve_profile(profile_name, profile_file)
    materialize_profile_env(profile)
    status = profile_env_status(profile)

    checks = {
        "env_file_exists": paths["env_file"].exists(),
        "profile_file_exists": resolve_profile_file(profile_file).exists(),
        "core_metrics_config_exists": resolve_core_metrics_config().exists(),
        "profile_url": status["url_present"],
        "profile_auth": status["auth_ok"],
    }

    result: dict[str, Any] = {
        "app_name": APP_NAME,
        "config_root": str(paths["config_root"]),
        "cache_root": str(paths["cache_root"]),
        "output_root": str(paths["output_root"]),
        "env_file": str(paths["env_file"]),
        "profile_file": str(resolve_profile_file(profile_file)),
        "core_metrics_config": str(resolve_core_metrics_config()),
        "profile": profile.get("profile_name"),
        "canonical_source_id": profile.get("canonical_source_id", ""),
        "checks": checks,
        "profile_env": status,
        "placeholder_env_vars": placeholder_env_vars(),
    }

    if real and checks["profile_url"] and checks["profile_auth"]:
        try:
            client = GrafanaClient.from_env(profile.get("canonical_source_id", ""))
            connection_ok = client.test_connection()
            result["checks"]["connection_test"] = connection_ok
        except Exception as exc:
            result["checks"]["connection_test"] = False
            result["connection_error"] = str(exc)

    result["ok"] = all(result["checks"].values()) and not result["placeholder_env_vars"]
    return result
