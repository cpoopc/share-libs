from __future__ import annotations

import os
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def get_app_root() -> Path:
    override = os.getenv("IVA_LOGTRACER_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return PACKAGE_ROOT


def get_output_root() -> Path:
    override = os.getenv("IVA_LOGTRACER_OUTPUT_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return get_app_root() / "output" / "iva_session"


def resolve_env_file(env_name: str | None = None) -> Path:
    explicit = os.getenv("IVA_LOGTRACER_ENV_FILE")
    if explicit:
        env_file = Path(explicit).expanduser().resolve()
    else:
        suffix = f".{env_name}" if env_name else ""
        env_file = get_app_root() / f".env{suffix}"

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
