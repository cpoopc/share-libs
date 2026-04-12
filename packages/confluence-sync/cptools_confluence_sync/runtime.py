from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from cptools_common.config import load_dotenv


APP_NAME = "confluence-sync"
DEFAULT_ENV_TEMPLATE = """# Confluence credentials
CONFLUENCE_USERNAME="your-email@example.com"
CONFLUENCE_TOKEN="your-confluence-token"

# Confluence settings
CONFLUENCE_URL="https://wiki.ringcentral.com"
CONFLUENCE_USE_BEARER="true"
CONFLUENCE_OUTPUT_DIR=""

# Translation backends
OPENAI_API_KEY=""
TENCENT_SECRET_ID=""
TENCENT_SECRET_KEY=""
"""

DEFAULT_CONFIG_TEMPLATE = """# Confluence Sync Configuration
confluence:
  url: "${CONFLUENCE_URL}"
  auth:
    username: "${CONFLUENCE_USERNAME}"
    token: "${CONFLUENCE_TOKEN}"
    use_bearer: true

spaces:
  - key: "IVA"
    output_dir: "${CONFLUENCE_OUTPUT_DIR}"
    flat: true
    hierarchy_depth: 2

exclude:
  titles:
    - "^Archive.*"
    - ".*\\(deprecated\\)$"
    - "^Meeting Notes.*"
    - "^Draft:.*"
  labels:
    - "deprecated"
    - "draft"
    - "internal"
    - "archived"
  ancestors:
    - "Archive"
    - "Meeting Notes"
    - "Trash"
    - "Templates"

sync:
  incremental: true
  state_file: ".sync_state.json"
  max_workers: 5
  download_images: true

upload:
  default_space: "IVA"
  state_file: ".upload_state.json"
  converter:
    heading_anchors: true
    skip_title_heading: true
    render_mermaid: false
    render_drawio: false
    alignment: "center"
  behavior:
    update_frontmatter: true
    check_conflicts: true
    title_mismatch_strategy: "keep-page-title"
    verify_upload: true
    mermaid_artifact_dir: ".artifacts/mermaid"
"""


def get_config_root() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME


def get_cache_root() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / APP_NAME


def get_output_root() -> Path:
    return get_cache_root() / "output"


def resolve_env_file(env_name: str | None = None) -> Path:
    config_root = get_config_root()
    if env_name:
        return config_root / f".env.{env_name}"
    return config_root / ".env"


def resolve_config_file(config_file: str | os.PathLike[str] | None = None) -> Path:
    if config_file:
        return Path(config_file).expanduser()
    return get_config_root() / "config.yaml"


def resolve_mermaid_bin() -> str | None:
    direct = shutil.which("mmdc")
    if direct:
        return direct

    cache_candidate = get_cache_root() / "bin" / "mmdc"
    if cache_candidate.exists():
        return str(cache_candidate)
    return None


def ensure_layout(force: bool = False) -> dict[str, Any]:
    config_root = get_config_root()
    cache_root = get_cache_root()
    output_root = get_output_root()
    (cache_root / "bin").mkdir(parents=True, exist_ok=True)
    (cache_root / "artifacts").mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    config_root.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    text_files = {
        config_root / ".env": DEFAULT_ENV_TEMPLATE,
        config_root / ".env.example": DEFAULT_ENV_TEMPLATE,
        config_root / ".env.lab": DEFAULT_ENV_TEMPLATE,
        config_root / ".env.production": DEFAULT_ENV_TEMPLATE,
        config_root / "config.yaml": DEFAULT_CONFIG_TEMPLATE,
    }
    for path, content in text_files.items():
        if force or not path.exists():
            path.write_text(content, encoding="utf-8")
            created.append(str(path))

    return {
        "config_root": str(config_root),
        "cache_root": str(cache_root),
        "output_root": str(output_root),
        "config_file": str(resolve_config_file()),
        "created": created,
    }


def load_runtime_env(env_name: str | None = None, env_file: str | None = None) -> dict[str, Path]:
    config_root = get_config_root()
    cache_root = get_cache_root()
    output_root = get_output_root()
    config_root.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    selected_env_file = Path(env_file).expanduser() if env_file else resolve_env_file(env_name)
    load_dotenv(selected_env_file, override=True)

    if not os.environ.get("CONFLUENCE_OUTPUT_DIR"):
        os.environ["CONFLUENCE_OUTPUT_DIR"] = str(output_root)
    if not os.environ.get("CONFLUENCE_USE_BEARER"):
        os.environ["CONFLUENCE_USE_BEARER"] = "true"

    return {
        "config_root": config_root,
        "cache_root": cache_root,
        "output_root": output_root,
        "env_file": selected_env_file,
        "config_file": resolve_config_file(),
    }


def doctor(
    env_name: str | None = None,
    env_file: str | None = None,
    config_file: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    paths = load_runtime_env(env_name=env_name, env_file=env_file)
    config_path = resolve_config_file(config_file)
    mmdc = resolve_mermaid_bin()

    checks = {
        "env_file_exists": paths["env_file"].exists(),
        "config_file_exists": config_path.exists(),
        "confluence_url": bool(os.environ.get("CONFLUENCE_URL")),
        "confluence_username": bool(os.environ.get("CONFLUENCE_USERNAME")),
        "confluence_token": bool(os.environ.get("CONFLUENCE_TOKEN")),
        "confluence_output_dir": bool(os.environ.get("CONFLUENCE_OUTPUT_DIR")),
        "mmdc_available": bool(mmdc),
    }

    return {
        "app_name": APP_NAME,
        "config_root": str(paths["config_root"]),
        "cache_root": str(paths["cache_root"]),
        "output_root": str(paths["output_root"]),
        "env_file": str(paths["env_file"]),
        "config_file": str(config_path),
        "selected_env": env_name or "default",
        "mmdc": mmdc or "",
        "checks": checks,
        "ok": all(
            checks[key]
            for key in (
                "env_file_exists",
                "config_file_exists",
                "confluence_url",
                "confluence_username",
                "confluence_token",
                "confluence_output_dir",
            )
        ),
    }
