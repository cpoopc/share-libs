#!/usr/bin/env bash

set -euo pipefail

APP_NAME="confluence-sync"
SKILL_NAME="confluence"
REMOTE_PACKAGE_SOURCE="git+ssh://git@github.com/cpoopc/share-libs.git#subdirectory=packages/confluence-sync"
REMOTE_SKILL_SOURCE="https://github.com/cpoopc/share-libs"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PACKAGE_SOURCE="$REMOTE_PACKAGE_SOURCE"
SKILL_SOURCE="$REMOTE_SKILL_SOURCE"
INSTALL_SKILL=1
RUN_INIT=1
DRY_RUN=0
SKILL_SCOPE_FLAG="-g"
SKILL_INSTALL_MODE="install"
CLI_INSTALL_MODE="auto"

usage() {
    cat <<'EOF'
Install confluence-sync CLI and the optional Codex-compatible skill.

Usage:
  ./install.sh [--editable-cli|--release-cli] [--skip-skill] [--skip-init] [--project-skill] [--skill-mode install|symlink] [--dry-run]

Options:
  --editable-cli Install the CLI from the local checkout in editable mode (best for development)
  --release-cli  Install the packaged CLI from the remote git source (best for release validation)
  --skip-skill    Install only the CLI, skip `npx skills add`
  --skip-init     Skip `confluence-sync init`
  --project-skill Install the skill in project scope instead of global scope
  --skill-mode    Skill install mode: `install` (managed copy, default) or `symlink` (dev mode)
  --symlink-skill Shortcut for `--skill-mode symlink`
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

resolve_cli_install_source() {
    case "$CLI_INSTALL_MODE" in
        auto)
            if [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
                CLI_INSTALL_MODE="editable"
                PACKAGE_SOURCE="$SCRIPT_DIR"
            else
                CLI_INSTALL_MODE="release"
                PACKAGE_SOURCE="$REMOTE_PACKAGE_SOURCE"
            fi
            ;;
        editable)
            [ -f "$SCRIPT_DIR/pyproject.toml" ] || die "--editable-cli requires a local checkout with $SCRIPT_DIR/pyproject.toml"
            PACKAGE_SOURCE="$SCRIPT_DIR"
            ;;
        release)
            PACKAGE_SOURCE="$REMOTE_PACKAGE_SOURCE"
            ;;
        *)
            die "Unsupported CLI install mode: $CLI_INSTALL_MODE"
            ;;
    esac
}

install_cli() {
    if [ "$CLI_INSTALL_MODE" = "editable" ]; then
        log "Installing CLI in editable mode from $PACKAGE_SOURCE"
        run_cmd uv tool install --force --editable "$PACKAGE_SOURCE"
    else
        log "Installing CLI in release mode from $PACKAGE_SOURCE"
        run_cmd uv tool install --force "$PACKAGE_SOURCE"
    fi
}

skill_target_root() {
    if [ -n "$SKILL_SCOPE_FLAG" ]; then
        printf '%s\n' "$HOME/.agents/skills"
    else
        printf '%s\n' "$PWD/.agents/skills"
    fi
}

install_skill_via_skills_cli() {
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
}

symlink_skill_into_target() {
    local skill_dir target_root target_path backup_dir backup_path current_target
    skill_dir="$REPO_ROOT/agents/skills/$SKILL_NAME"
    [ -f "$skill_dir/SKILL.md" ] || die "Symlink skill mode requires a local checkout with $skill_dir"

    target_root="$(skill_target_root)"
    target_path="$target_root/$SKILL_NAME"
    run_cmd mkdir -p "$target_root"

    if [ -L "$target_path" ]; then
        current_target="$(readlink "$target_path" || true)"
        if [ "$current_target" = "$skill_dir" ]; then
            log "Skill '$SKILL_NAME' already symlinked at $target_path"
            return 0
        fi
        run_cmd rm "$target_path"
    elif [ -e "$target_path" ]; then
        backup_dir="$target_root/.backup"
        backup_path="$backup_dir/${SKILL_NAME}-$(date +%Y%m%d-%H%M%S)"
        run_cmd mkdir -p "$backup_dir"
        run_cmd mv "$target_path" "$backup_path"
        log "Backed up existing skill to $backup_path"
    fi

    log "Symlinking skill '$SKILL_NAME' to $skill_dir"
    run_cmd ln -s "$skill_dir" "$target_path"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --editable-cli) CLI_INSTALL_MODE="editable" ;;
        --release-cli) CLI_INSTALL_MODE="release" ;;
        --skip-skill) INSTALL_SKILL=0 ;;
        --skip-init) RUN_INIT=0 ;;
        --project-skill) SKILL_SCOPE_FLAG="" ;;
        --skill-mode)
            shift
            [ "$#" -gt 0 ] || die "Missing value for --skill-mode"
            case "$1" in
                install|symlink) SKILL_INSTALL_MODE="$1" ;;
                *) die "Unsupported skill mode: $1 (expected install or symlink)" ;;
            esac
            ;;
        --symlink-skill) SKILL_INSTALL_MODE="symlink" ;;
        --dry-run) DRY_RUN=1 ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown option: $1" ;;
    esac
    shift
done

if [ -f "$REPO_ROOT/agents/skills/$SKILL_NAME/SKILL.md" ]; then
    SKILL_SOURCE="$REPO_ROOT"
fi

require_cmd uv
resolve_cli_install_source

install_cli

if [ "$INSTALL_SKILL" -eq 1 ]; then
    if [ "$SKILL_INSTALL_MODE" = "install" ]; then
        install_skill_via_skills_cli
    else
        log "Using symlink dev mode for skill '$SKILL_NAME'"
        install_skill_via_skills_cli
        symlink_skill_into_target
    fi
fi

if [ "$RUN_INIT" -eq 1 ]; then
    log "Initializing XDG workspace"
    run_cmd uv tool run --from "$PACKAGE_SOURCE" confluence-sync init
fi

log "Bootstrap complete"
log "If '$APP_NAME' is not on PATH yet, run: uv tool update-shell"
log "Next steps:"
log "  1. Fill ~/.config/$APP_NAME/.env or ~/.config/$APP_NAME/.env.production"
log "  2. Review ~/.config/$APP_NAME/config.yaml"
log "  3. Run: confluence-sync doctor --real"
