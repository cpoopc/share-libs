from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Sequence

from cptools_common import load_dotenv


APP_NAME = "jira-ticket-sync"
DEFAULT_JIRA_URL = "https://jira.ringcentral.com"
PLACEHOLDER_VALUES = {
    "JIRA_URL": {
        "https://jira.example.com",
        "http://jira.example.com",
        "https://example.com",
        "http://example.com",
    },
    "JIRA_USERNAME": {
        "your.name@example.com",
        "user@example.com",
    },
    "JIRA_TOKEN": {
        "replace-with-api-token",
        "your-api-token",
        "changeme",
    },
}


def package_workspace_root() -> Path:
    return Path(__file__).resolve().parent / "assets" / "workspace"


def _xdg_dir(env_var: str, fallback_suffix: str) -> Path:
    override = os.getenv(env_var)
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / fallback_suffix).resolve()


def get_config_root() -> Path:
    override = os.getenv("JIRA_TICKET_SYNC_HOME") or os.getenv("JIRA_TICKET_SYNC_WORKSPACE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return _xdg_dir("XDG_CONFIG_HOME", ".config") / APP_NAME


def get_cache_root() -> Path:
    override = os.getenv("JIRA_TICKET_SYNC_CACHE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return _xdg_dir("XDG_CACHE_HOME", ".cache") / APP_NAME


def get_output_root() -> Path:
    override = os.getenv("JIRA_TICKET_SYNC_OUTPUT_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return get_cache_root() / "output"


def get_default_env_path(env_name: str | None = None) -> Path:
    suffix = f".{env_name}" if env_name else ""
    return get_config_root() / f".env{suffix}"


def default_workspace_root() -> Path:
    config_root = get_config_root()
    if (
        (config_root / "project-config.yaml").exists()
        or (config_root / "manifests").exists()
        or (config_root / "profiles").exists()
    ):
        return config_root
    return package_workspace_root()


def _path(value: str | None) -> Path | None:
    return Path(value).expanduser() if value else None


def resolve_workspace_paths(
    *,
    workspace_root: str | Path | None = None,
    manifest_root: str | Path | None = None,
    profile_root: str | Path | None = None,
    template_root: str | Path | None = None,
    project_config: str | Path | None = None,
    state_file: str | Path | None = None,
    field_classification_root: str | Path | None = None,
) -> dict[str, Path]:
    resolved_workspace_root = (
        _path(str(workspace_root)) if workspace_root is not None else None
    ) or _path(os.getenv("JIRA_TICKET_SYNC_WORKSPACE_ROOT")) or default_workspace_root()

    resolved_manifest_root = (
        _path(str(manifest_root)) if manifest_root is not None else None
    ) or _path(os.getenv("JIRA_TICKET_SYNC_MANIFEST_ROOT")) or (resolved_workspace_root / "manifests")

    resolved_profile_root = (
        _path(str(profile_root)) if profile_root is not None else None
    ) or _path(os.getenv("JIRA_TICKET_SYNC_PROFILE_ROOT")) or (resolved_workspace_root / "profiles")

    resolved_template_root = (
        _path(str(template_root)) if template_root is not None else None
    ) or _path(os.getenv("JIRA_TICKET_SYNC_TEMPLATE_ROOT")) or (resolved_workspace_root / "templates" / "imported")

    resolved_project_config = (
        _path(str(project_config)) if project_config is not None else None
    ) or _path(os.getenv("JIRA_TICKET_SYNC_PROJECT_CONFIG_PATH")) or (resolved_workspace_root / "project-config.yaml")

    resolved_state_file = (
        _path(str(state_file)) if state_file is not None else None
    ) or _path(os.getenv("JIRA_TICKET_SYNC_STATE_FILE")) or (resolved_workspace_root / "state" / "sync-state.json")

    resolved_field_classification_root = (
        _path(str(field_classification_root)) if field_classification_root is not None else None
    ) or _path(os.getenv("JIRA_TICKET_SYNC_FIELD_CLASSIFICATION_ROOT")) or (
        resolved_workspace_root / "state" / "field-classification"
    )

    return {
        "workspace_root": resolved_workspace_root,
        "manifest_root": resolved_manifest_root,
        "profile_root": resolved_profile_root,
        "template_root": resolved_template_root,
        "project_config": resolved_project_config,
        "state_file": resolved_state_file,
        "field_classification_root": resolved_field_classification_root,
    }


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


def _copy_workspace_tree(source_dir: Path, target_dir: Path, *, force: bool = False) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for child in source_dir.iterdir():
        destination = target_dir / child.name
        if child.is_dir():
            if force and destination.exists():
                shutil.rmtree(destination)
            if destination.exists():
                _copy_workspace_tree(child, destination, force=force)
            else:
                shutil.copytree(child, destination)
            continue
        if force or not destination.exists():
            shutil.copy2(child, destination)


def init_runtime_home(*, force: bool = False, env_name: str | None = None) -> dict[str, Path]:
    paths = ensure_runtime_layout()
    config_root = paths["config_root"]
    source_dir = package_workspace_root()
    if not source_dir.is_dir():
        raise ValueError(f"Bundled workspace assets not found: {source_dir}")

    _copy_workspace_tree(source_dir, config_root, force=force)

    example_path = config_root / ".env.example"
    env_path = get_default_env_path(env_name)
    if example_path.exists():
        if force or not env_path.exists():
            shutil.copy2(example_path, env_path)
    elif force or not env_path.exists():
        env_path.write_text("", encoding="utf-8")

    paths["workspace_root"] = config_root
    paths["env_path"] = env_path
    paths["example_path"] = example_path
    return paths


def get_runtime_diagnostics(env_name: str | None = None) -> dict[str, object]:
    config_root = get_config_root()
    cache_root = get_cache_root()
    output_root = get_output_root()
    env_path = get_default_env_path(env_name)
    paths = resolve_workspace_paths(workspace_root=config_root if config_root.exists() else None)
    return {
        "config_root": config_root,
        "cache_root": cache_root,
        "output_root": output_root,
        "workspace_root": paths["workspace_root"],
        "manifest_root": paths["manifest_root"],
        "profile_root": paths["profile_root"],
        "template_root": paths["template_root"],
        "project_config": paths["project_config"],
        "state_file": paths["state_file"],
        "field_classification_root": paths["field_classification_root"],
        "env_path": env_path,
        "env_exists": env_path.exists(),
        "config_exists": config_root.exists(),
        "cache_exists": cache_root.exists(),
        "output_exists": output_root.exists(),
        "uses_packaged_workspace": paths["workspace_root"] == package_workspace_root(),
        "missing_env_vars": missing_env_vars(),
        "placeholder_env_vars": placeholder_env_vars(),
    }


def bootstrap_workspace(target: str | Path, *, force: bool = False, dry_run: bool = False) -> list[str]:
    source_dir = package_workspace_root()
    target_dir = Path(target).expanduser().resolve()

    if not source_dir.is_dir():
        raise ValueError(f"Bundled workspace assets not found: {source_dir}")

    messages: list[str] = []
    if target_dir.exists():
        if not force:
            raise ValueError(f"Target already exists: {target_dir}. Pass --force to replace it.")
        if dry_run:
            messages.append(f"Would remove existing target: {target_dir}")
        else:
            shutil.rmtree(target_dir)

    if dry_run:
        messages.append(f"Would copy {source_dir} -> {target_dir}")
        return messages

    target_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, target_dir)
    messages.append(f"Bootstrapped workspace: {target_dir}")
    return messages


def _workspace_root_from_path(path: Path) -> Path | None:
    expanded = path.expanduser()

    if expanded.name == ".env":
        return expanded.parent
    if expanded.name == "project-config.yaml":
        return expanded.parent
    if expanded.name == "manifests":
        return expanded.parent
    if expanded.name == "profiles":
        return expanded.parent
    if expanded.name == "field-classification":
        state_dir = expanded.parent
        if state_dir.name == "state":
            return state_dir.parent
    if expanded.name == "sync-state.json" and expanded.parent.name == "state":
        return expanded.parent.parent
    if expanded.parent.name == "profiles":
        return expanded.parent.parent
    if expanded.parent.name == "field-classification" and expanded.parent.parent.name == "state":
        return expanded.parent.parent.parent

    for parent in (expanded, *expanded.parents):
        if parent.name == "manifests":
            return parent.parent

    if expanded.suffix in {".yaml", ".yml", ".json"}:
        return expanded.parent
    if expanded.is_dir():
        return expanded

    return None


def _extract_flag_path(argv: Sequence[str], flag_name: str) -> Path | None:
    i = 0
    while i < len(argv):
        if argv[i] == flag_name and i + 1 < len(argv):
            return Path(argv[i + 1]).expanduser()
        i += 1
    return None


def discover_workspace_env_files(argv: Sequence[str]) -> list[Path]:
    env_files: list[Path] = []

    def add_workspace_env(path_str: str) -> None:
        workspace_root = _workspace_root_from_path(Path(path_str))
        if workspace_root is None:
            return
        candidate = workspace_root / ".env"
        if candidate not in env_files:
            env_files.append(candidate)

    if argv and argv[0] in {"status", "push", "pull"} and len(argv) >= 2:
        add_workspace_env(argv[1])

    flags_with_paths = {
        "--jira-project-config",
        "--profile",
        "--profile-root",
        "--state-file",
        "--field-classification-cache",
        "--field-classification-root",
        "--workspace-root",
        "--manifest-root",
    }

    i = 0
    while i < len(argv):
        if argv[i] in flags_with_paths and i + 1 < len(argv):
            add_workspace_env(argv[i + 1])
            i += 2
            continue
        i += 1

    return env_files


def discover_workspace_project_config(argv: Sequence[str]) -> Path | None:
    explicit = _extract_flag_path(argv, "--jira-project-config")
    if explicit is not None:
        return explicit

    candidate_paths: list[Path] = []

    if argv and argv[0] in {"status", "push", "pull"} and len(argv) >= 2:
        candidate_paths.append(Path(argv[1]).expanduser())

    for flag_name in (
        "--profile",
        "--profile-root",
        "--state-file",
        "--field-classification-cache",
        "--field-classification-root",
        "--workspace-root",
        "--manifest-root",
    ):
        candidate = _extract_flag_path(argv, flag_name)
        if candidate is not None:
            candidate_paths.append(candidate)

    candidate_paths.append(Path.cwd())
    candidate_paths.append(package_workspace_root())

    for candidate_path in candidate_paths:
        workspace_root = _workspace_root_from_path(candidate_path)
        if workspace_root is not None:
            project_config = workspace_root / "project-config.yaml"
            if project_config.exists():
                return project_config
        if candidate_path.name == "project-config.yaml" and candidate_path.exists():
            return candidate_path
        if candidate_path.is_dir():
            project_config = candidate_path / "project-config.yaml"
            if project_config.exists():
                return project_config

    default_path = package_workspace_root() / "project-config.yaml"
    if default_path.exists():
        return default_path
    return None


def extract_env_files(argv: Sequence[str]) -> tuple[list[Path], list[str]]:
    env_files: list[Path] = []
    remaining: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--env-file":
            if i + 1 >= len(argv):
                raise ValueError("--env-file requires a path")
            env_files.append(Path(argv[i + 1]).expanduser())
            i += 2
            continue
        remaining.append(arg)
        i += 1
    return env_files, remaining


def existing_env_files(paths: Sequence[Path]) -> list[Path]:
    existing: list[Path] = []
    for path in paths:
        expanded = path.expanduser()
        if expanded.exists() and expanded not in existing:
            existing.append(expanded)
    return existing


def load_env_files(paths: Sequence[Path]) -> list[Path]:
    loaded = load_dotenv(*paths, override=True)
    os.environ.setdefault("JIRA_URL", DEFAULT_JIRA_URL)
    return loaded


def requires_jira_env(argv: Sequence[str]) -> bool:
    return "--real" in argv


def missing_env_vars() -> list[str]:
    missing = []
    use_bearer = os.getenv("JIRA_USE_BEARER", "").lower() in {"1", "true", "yes"}
    if not os.getenv("JIRA_TOKEN"):
        missing.append("JIRA_TOKEN")
    if not use_bearer and not os.getenv("JIRA_USERNAME"):
        missing.append("JIRA_USERNAME")
    return missing


def placeholder_env_vars() -> list[str]:
    placeholders = []
    use_bearer = os.getenv("JIRA_USE_BEARER", "").lower() in {"1", "true", "yes"}

    for key, sentinel_values in PLACEHOLDER_VALUES.items():
        if key == "JIRA_USERNAME" and use_bearer:
            continue
        value = os.getenv(key, "").strip()
        if value and value in sentinel_values:
            placeholders.append(key)

    return placeholders


def format_first_use_setup() -> str:
    example_env = get_config_root() / ".env.example"
    return "\n".join(
        [
            "Real Jira operation requires first-time setup.",
            "",
            "Run this once to create the default workspace:",
            "  jira-ticket-sync init",
            "",
            "Required environment variables:",
            "  JIRA_TOKEN",
            "  JIRA_USERNAME  (required unless JIRA_USE_BEARER=true)",
            "",
            "Optional environment variables:",
            f"  JIRA_URL={DEFAULT_JIRA_URL}",
            "  JIRA_USE_BEARER=true",
            "  JIRA_STORY_POINTS_FIELD=customfield_10016",
            "",
            "Workspace config files to prepare or keep:",
            "  manifests/*.yaml",
            "  profiles/<PROJECT>.yaml",
            "  project-config.yaml",
            "  state/field-classification/<PROJECT>.json",
            "  state/sync-state.json",
            "",
            f"Copy this template first: {example_env}",
            "Example:",
            "  cp ~/.config/jira-ticket-sync/.env.example ~/.config/jira-ticket-sync/.env",
            "  edit the values, then rerun the command",
        ]
    )


def prepare_cli_environment(argv: Sequence[str]) -> list[str]:
    env_files, remaining = extract_env_files(argv)
    candidate_env_files = [
        *env_files,
        *discover_workspace_env_files(remaining),
        get_default_env_path(),
        Path.cwd() / ".env",
        package_workspace_root() / ".env",
    ]
    existing = existing_env_files(candidate_env_files)
    load_env_files(candidate_env_files)

    if "JIRA_PROJECT_CONFIG_PATH" not in os.environ and "--jira-project-config" not in remaining:
        project_config = discover_workspace_project_config(remaining)
        if project_config is not None:
            os.environ["JIRA_PROJECT_CONFIG_PATH"] = str(project_config)

    if requires_jira_env(remaining):
        missing = missing_env_vars()
        placeholders = placeholder_env_vars()
        if not existing and missing:
            raise ValueError(
                format_first_use_setup() + "\n\nNo configured .env file found. Configure .env first, then rerun."
            )
        if missing or placeholders:
            details: list[str] = []
            if missing:
                details.append(f"Missing: {', '.join(missing)}")
            if placeholders:
                details.append(f"Still using placeholder values: {', '.join(placeholders)}")
            raise ValueError(format_first_use_setup() + "\n\n" + "\n".join(details))

    return remaining
