#!/usr/bin/env bash

set -euo pipefail

APP_NAME="share-libs-bootstrap-all"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
INSTALL_CLIS=1
INSTALL_SKILLS=1
RUN_INIT=1
DRY_RUN=0
SKILL_SCOPE_FLAG="-g"
SKILL_INSTALL_MODE="install"

usage() {
    cat <<'EOF'
Install the main share-libs CLIs from the current checkout and then install all share-libs skills.

Usage:
  ./bootstrap-all.sh [--skip-clis] [--skip-skills] [--skip-init] [--project-skill] [--skill-mode install|symlink] [--dry-run]

Options:
  --skip-clis     Skip CLI installation and initialization
  --skip-skills   Skip skill installation
  --skip-init     Pass `--skip-init` to package install scripts
  --project-skill Install skills in project scope instead of global scope
  --skill-mode    Skill install mode: `install` (managed copy, default) or `symlink` (dev mode)
  --symlink-skills Shortcut for `--skill-mode symlink`
  --dry-run       Execute nested scripts in dry-run mode
  -h, --help      Show this help
EOF
}

log() {
    printf '[%s] %s\n' "$APP_NAME" "$1"
}

die() {
    printf '[%s] ERROR: %s\n' "$APP_NAME" "$1" >&2
    exit 1
}

run_script() {
    local script_path="$1"
    shift
    if [ "$DRY_RUN" -eq 1 ]; then
        bash "$script_path" "$@" --dry-run
    else
        bash "$script_path" "$@"
    fi
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --skip-clis)
            INSTALL_CLIS=0
            ;;
        --skip-skills)
            INSTALL_SKILLS=0
            ;;
        --skip-init)
            RUN_INIT=0
            ;;
        --project-skill)
            SKILL_SCOPE_FLAG=""
            ;;
        --skill-mode)
            shift
            [ "$#" -gt 0 ] || die "Missing value for --skill-mode"
            case "$1" in
                install|symlink) SKILL_INSTALL_MODE="$1" ;;
                *) die "Unsupported skill mode: $1 (expected install or symlink)" ;;
            esac
            ;;
        --symlink-skills)
            SKILL_INSTALL_MODE="symlink"
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

CLI_INSTALL_SCRIPTS="
packages/confluence-sync/install.sh
packages/grafana-report-fetching/install.sh
packages/iva-logtracer/install.sh
packages/jira-ticket-sync/install.sh
tools/python/libs/kibana/install.sh
"

if [ "$INSTALL_CLIS" -eq 1 ]; then
    log "Installing shared CLIs from local checkout"
    printf '%s\n' "$CLI_INSTALL_SCRIPTS" | while IFS= read -r relative_script; do
        [ -n "$relative_script" ] || continue
        script_path="$REPO_ROOT/$relative_script"
        [ -f "$script_path" ] || die "Missing install script: $script_path"
        args=(--skip-skill)
        if [ "$RUN_INIT" -eq 0 ]; then
            args+=(--skip-init)
        fi
        run_script "$script_path" "${args[@]}"
    done
fi

if [ "$INSTALL_SKILLS" -eq 1 ]; then
    log "Installing all share-libs skills"
    skill_args=()
    if [ -z "$SKILL_SCOPE_FLAG" ]; then
        skill_args+=(--project-skill)
    fi
    if [ "$SKILL_INSTALL_MODE" != "install" ]; then
        skill_args+=(--skill-mode "$SKILL_INSTALL_MODE")
    fi
    if [ "${#skill_args[@]}" -gt 0 ]; then
        run_script "$REPO_ROOT/bootstrap-skills.sh" "${skill_args[@]}"
    else
        run_script "$REPO_ROOT/bootstrap-skills.sh"
    fi
fi

log "Bootstrap complete"
