#!/usr/bin/env bash

set -euo pipefail

APP_NAME="share-libs-installer"
DEFAULT_REPO_DIR="$HOME/cp-share-libs"
DEFAULT_REF="main"
SHARE_LIBS_SSH_URL="git@github.com:cpoopc/share-libs.git"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TARGET_DIR=""
REF="$DEFAULT_REF"
INSTALL_CLIS=1
INSTALL_SKILLS=1
SKILL_INSTALL_MODE="symlink"
SKILL_SCOPE_FLAG="-g"
DRY_RUN=0
CLONED_NEW_CHECKOUT=0

usage() {
    cat <<'EOF'
Clone or reuse a local share-libs checkout, then run bootstrap-all.sh.

Usage:
  ./install-share-libs.sh [--dir <path>] [--ref <branch-or-commit>] [--skip-clis] [--skip-skills] [--project-skill] [--managed-skills] [--dry-run]

Options:
  --dir <path>       Target checkout directory. Defaults to ~/cp-share-libs unless running from an existing share-libs checkout.
  --ref <ref>        Git branch, tag, or commit to check out when cloning a new checkout. Default: main
  --skip-clis        Skip CLI installation
  --skip-skills      Skip skill installation
  --project-skill    Install skills in project scope instead of global scope
  --managed-skills   Install skills in managed copy mode instead of symlink mode
  --dry-run          Print clone/bootstrap commands without executing them
  -h, --help         Show this help
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

expand_path() {
    local path="$1"
    case "$path" in
        "~")
            printf '%s\n' "$HOME"
            ;;
        "~/"*)
            printf '%s/%s\n' "$HOME" "${path#~/}"
            ;;
        /*)
            printf '%s\n' "$path"
            ;;
        *)
            printf '%s/%s\n' "$PWD" "$path"
            ;;
    esac
}

is_share_libs_remote_url() {
    local remote_url="$1"
    case "$remote_url" in
        git@github.com:cpoopc/share-libs|git@github.com:cpoopc/share-libs.git) return 0 ;;
        ssh://git@github.com/cpoopc/share-libs|ssh://git@github.com/cpoopc/share-libs.git) return 0 ;;
        https://github.com/cpoopc/share-libs|https://github.com/cpoopc/share-libs.git) return 0 ;;
        *) return 1 ;;
    esac
}

is_valid_share_libs_clone() {
    local candidate_dir="$1"
    local remote_url
    [ -d "$candidate_dir" ] || return 1
    [ -e "$candidate_dir/.git" ] || return 1
    [ -f "$candidate_dir/bootstrap-all.sh" ] || return 1
    [ -d "$candidate_dir/agents/skills" ] || return 1
    remote_url="$(git -C "$candidate_dir" remote get-url origin 2>/dev/null || true)"
    [ -n "$remote_url" ] || return 1
    is_share_libs_remote_url "$remote_url"
}

resolve_default_target_dir() {
    if is_valid_share_libs_clone "$SCRIPT_DIR"; then
        printf '%s\n' "$SCRIPT_DIR"
    else
        printf '%s\n' "$DEFAULT_REPO_DIR"
    fi
}

clone_or_reuse_checkout() {
    if [ -e "$TARGET_DIR" ]; then
        if ! [ -d "$TARGET_DIR" ]; then
            die "Target path exists but is not a directory: $TARGET_DIR"
        fi
        if is_valid_share_libs_clone "$TARGET_DIR"; then
            log "Reusing existing share-libs checkout at $TARGET_DIR"
            if [ "$REF" != "$DEFAULT_REF" ]; then
                warn "Ignoring --ref $REF because the target checkout already exists"
            fi
            return 0
        fi
        die "Target directory exists but is not a valid share-libs clone: $TARGET_DIR"
    fi

    log "Cloning share-libs to $TARGET_DIR"
    run_cmd mkdir -p "$(dirname "$TARGET_DIR")"
    run_cmd git clone "$SHARE_LIBS_SSH_URL" "$TARGET_DIR"
    CLONED_NEW_CHECKOUT=1

    if [ "$REF" != "$DEFAULT_REF" ]; then
        log "Checking out ref $REF"
        run_cmd git -C "$TARGET_DIR" checkout "$REF"
    fi
}

run_bootstrap() {
    local bootstrap_script="$TARGET_DIR/bootstrap-all.sh"
    local args=()

    if [ "$INSTALL_CLIS" -eq 0 ]; then
        args+=(--skip-clis)
    fi
    if [ "$INSTALL_SKILLS" -eq 0 ]; then
        args+=(--skip-skills)
    fi
    if [ -z "$SKILL_SCOPE_FLAG" ]; then
        args+=(--project-skill)
    fi
    if [ "$SKILL_INSTALL_MODE" = "symlink" ]; then
        args+=(--symlink-skills)
    fi

    if [ "$DRY_RUN" -eq 0 ] || [ "$CLONED_NEW_CHECKOUT" -eq 0 ]; then
        [ -f "$bootstrap_script" ] || die "Missing bootstrap script: $bootstrap_script"
    fi

    log "Running bootstrap from $TARGET_DIR"
    run_cmd bash "$bootstrap_script" "${args[@]}"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dir)
            shift
            [ "$#" -gt 0 ] || die "Missing value for --dir"
            TARGET_DIR="$(expand_path "$1")"
            ;;
        --ref)
            shift
            [ "$#" -gt 0 ] || die "Missing value for --ref"
            REF="$1"
            ;;
        --skip-clis)
            INSTALL_CLIS=0
            ;;
        --skip-skills)
            INSTALL_SKILLS=0
            ;;
        --project-skill)
            SKILL_SCOPE_FLAG=""
            ;;
        --managed-skills)
            SKILL_INSTALL_MODE="install"
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

if [ -z "$TARGET_DIR" ]; then
    TARGET_DIR="$(resolve_default_target_dir)"
fi

require_cmd git
if [ "$INSTALL_CLIS" -eq 1 ]; then
    require_cmd uv
fi
if [ "$INSTALL_SKILLS" -eq 1 ]; then
    require_cmd npx
fi

clone_or_reuse_checkout
run_bootstrap

log "Installer complete"
log "Checkout: $TARGET_DIR"
log "Local source edits will flow through editable CLIs and symlinked skills by default"
