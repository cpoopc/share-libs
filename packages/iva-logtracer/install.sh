#!/usr/bin/env bash

set -euo pipefail

APP_NAME="iva-logtracer"
SKILL_NAME="iva-logtracer"
REMOTE_PACKAGE_SOURCE="git+ssh://git@github.com/cpoopc/share-libs.git#subdirectory=packages/iva-logtracer"
REMOTE_SKILL_SOURCE="https://github.com/cpoopc/share-libs"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PACKAGE_SOURCE="$REMOTE_PACKAGE_SOURCE"
SKILL_SOURCE="$REMOTE_SKILL_SOURCE"
INSTALL_SKILL=1
RUN_INIT=1
DRY_RUN=0
SKILL_SCOPE_FLAG="-g"

usage() {
    cat <<'EOF'
Install iva-logtracer CLI and the optional Codex-compatible skill.

Usage:
  ./install.sh [--skip-skill] [--skip-init] [--project-skill] [--dry-run]

Options:
  --skip-skill    Install only the CLI, skip `npx skills add`
  --skip-init     Skip `iva-logtracer init` and env template creation
  --project-skill Install the skill in project scope instead of global scope
  --dry-run       Print commands without executing them
  -h, --help      Show this help
EOF
}

log() {
    printf '[%s] %s\n' "$APP_NAME" "$1"
}

warn() {
    printf '[%s] WARN: %s\n' "$APP_NAME" "$1" >&2
}

die() {
    printf '[%s] ERROR: %s\n' "$APP_NAME" "$1" >&2
    exit 1
}

run_cmd() {
    if [ "$DRY_RUN" -eq 1 ]; then
        printf '+'
        for arg in "$@"; do
            printf ' %q' "$arg"
        done
        printf '\n'
        return 0
    fi
    "$@"
}

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

ensure_env_variants() {
    local config_home config_root example_path env_name env_path
    config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
    config_root="$config_home/$APP_NAME"
    example_path="$config_root/.env.example"

    [ -f "$example_path" ] || return 0

    for env_name in lab production; do
        env_path="$config_root/.env.$env_name"
        if [ ! -f "$env_path" ]; then
            run_cmd cp "$example_path" "$env_path"
            log "Created $env_path"
        fi
    done
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --skip-skill)
            INSTALL_SKILL=0
            ;;
        --skip-init)
            RUN_INIT=0
            ;;
        --project-skill)
            SKILL_SCOPE_FLAG=""
            ;;
        --dry-run)
            DRY_RUN=1
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown option: $1"
            ;;
    esac
    shift
done

if [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
    PACKAGE_SOURCE="$SCRIPT_DIR"
fi

if [ -f "$REPO_ROOT/agents/skills/$SKILL_NAME/SKILL.md" ]; then
    SKILL_SOURCE="$REPO_ROOT"
fi

require_cmd uv

log "Installing CLI from $PACKAGE_SOURCE"
run_cmd uv tool install --force "$PACKAGE_SOURCE"

if [ "$INSTALL_SKILL" -eq 1 ]; then
    if command -v npx >/dev/null 2>&1; then
        log "Installing skill '$SKILL_NAME' from $SKILL_SOURCE"
        if [ -n "$SKILL_SCOPE_FLAG" ]; then
            run_cmd npx --yes skills add "$SKILL_SOURCE" --skill "$SKILL_NAME" "$SKILL_SCOPE_FLAG" -y
        else
            run_cmd npx --yes skills add "$SKILL_SOURCE" --skill "$SKILL_NAME" -y
        fi
    else
        warn "npx not found; skipping skill installation"
    fi
fi

if [ "$RUN_INIT" -eq 1 ]; then
    log "Initializing XDG config and cache directories"
    run_cmd uv tool run --from "$PACKAGE_SOURCE" iva-logtracer init
    ensure_env_variants
fi

log "Bootstrap complete"
log "If '$APP_NAME' is not on PATH yet, run: uv tool update-shell"
log "Next steps:"
log "  1. Fill ~/.config/$APP_NAME/.env.production and ~/.env.lab if needed"
log "  2. Run: iva-logtracer doctor --env production"
