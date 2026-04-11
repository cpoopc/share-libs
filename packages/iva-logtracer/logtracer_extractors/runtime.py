from __future__ import annotations

import os
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "iva-logtracer"
DEFAULT_ENV_TEMPLATE = """# IVA Logtracer configuration
KIBANA_ES_URL=
KIBANA_USERNAME=
KIBANA_PASSWORD=
KIBANA_INDEX=*:*-logs-air_assistant_runtime-*
KIBANA_VERIFY_CERTS=true
"""


def _xdg_dir(env_var: str, fallback_suffix: str) -> Path:
    override = os.getenv(env_var)
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / fallback_suffix).resolve()


def get_config_root() -> Path:
    override = os.getenv("IVA_LOGTRACER_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return _xdg_dir("XDG_CONFIG_HOME", ".config") / APP_NAME


def get_cache_root() -> Path:
    override = os.getenv("IVA_LOGTRACER_CACHE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return _xdg_dir("XDG_CACHE_HOME", ".cache") / APP_NAME


def get_app_root() -> Path:
    return get_config_root()


def get_output_root() -> Path:
    override = os.getenv("IVA_LOGTRACER_OUTPUT_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return get_cache_root() / "output" / "iva_session"


def get_default_env_path(env_name: str | None = None) -> Path:
    suffix = f".{env_name}" if env_name else ""
    return get_config_root() / f".env{suffix}"


def ensure_runtime_layout() -> dict[str, Path]:
    config_root = get_config_root()
    cache_root = get_cache_root()
    output_root = get_output_root()
    config_root.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    return {
        "config_root": config_root,
        "cache_root": cache_root,
        "output_root": output_root,
    }


def init_runtime_home(*, force: bool = False, env_name: str | None = None) -> dict[str, Path]:
    paths = ensure_runtime_layout()
    env_path = get_default_env_path(env_name)
    example_path = paths["config_root"] / ".env.example"
    example_path.write_text(DEFAULT_ENV_TEMPLATE, encoding="utf-8")

    if force or not env_path.exists():
        env_path.write_text(DEFAULT_ENV_TEMPLATE, encoding="utf-8")

    paths["env_path"] = env_path
    paths["example_path"] = example_path
    return paths


def resolve_env_file(env_name: str | None = None) -> Path:
    explicit = os.getenv("IVA_LOGTRACER_ENV_FILE")
    if explicit:
        env_file = Path(explicit).expanduser().resolve()
    else:
        env_file = get_default_env_path(env_name)

    if not env_file.exists():
        raise FileNotFoundError(f"Environment file not found: {env_file}")

    return env_file


def load_env_file(env_name: str | None = None) -> Path:
    env_file = resolve_env_file(env_name)

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]

        os.environ[key] = value

    return env_file


def get_runtime_diagnostics(env_name: str | None = None) -> dict[str, object]:
    config_root = get_config_root()
    cache_root = get_cache_root()
    output_root = get_output_root()
    env_path = get_default_env_path(env_name)

    diagnostics: dict[str, object] = {
        "package_root": PACKAGE_ROOT,
        "config_root": config_root,
        "cache_root": cache_root,
        "output_root": output_root,
        "env_path": env_path,
        "env_exists": env_path.exists(),
        "output_exists": output_root.exists(),
        "config_exists": config_root.exists(),
    }

    if env_path.exists():
        try:
            load_env_file(env_name)
        except Exception as exc:  # pragma: no cover - surfaced in doctor output
            diagnostics["env_load_error"] = str(exc)
        else:
            diagnostics["required_vars"] = {
                "KIBANA_ES_URL": bool(os.getenv("KIBANA_ES_URL") or os.getenv("KIBANA_URL")),
                "KIBANA_USERNAME": bool(os.getenv("KIBANA_USERNAME")),
                "KIBANA_PASSWORD": bool(os.getenv("KIBANA_PASSWORD") or os.getenv("KIBANA_API_KEY")),
            }
    return diagnostics
