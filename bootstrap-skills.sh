#!/usr/bin/env bash

set -euo pipefail

APP_NAME="share-libs-bootstrap-skills"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
SKILL_SCOPE_FLAG="-g"
SKILL_INSTALL_MODE="install"
DRY_RUN=0

usage() {
    cat <<'EOF'
Install all share-libs skills from the current local checkout.

Usage:
  ./bootstrap-skills.sh [--project-skill] [--skill-mode install|symlink] [--dry-run]

Options:
  --project-skill Install skills in project scope instead of global scope
  --skill-mode    Skill install mode: `install` (managed copy, default) or `symlink` (dev mode)
  --symlink-skills Shortcut for `--skill-mode symlink`
  --dry-run       Print nested install commands without executing them
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

skill_target_root() {
    if [ -n "$SKILL_SCOPE_FLAG" ]; then
        printf '%s\n' "$HOME/.agents/skills"
    else
        printf '%s\n' "$PWD/.agents/skills"
    fi
}

install_skill_via_skills_cli() {
    local skill_name="$1"
    log "Installing skill '$skill_name' from $REPO_ROOT"
    if [ "$DRY_RUN" -eq 1 ]; then
        if [ -n "$SKILL_SCOPE_FLAG" ]; then
            run_cmd npx --yes skills add "$REPO_ROOT" --skill "$skill_name" "$SKILL_SCOPE_FLAG" -y
        else
            run_cmd npx --yes skills add "$REPO_ROOT" --skill "$skill_name" -y
        fi
        return 0
    fi
    if [ -n "$SKILL_SCOPE_FLAG" ]; then
        npx --yes skills add "$REPO_ROOT" --skill "$skill_name" "$SKILL_SCOPE_FLAG" -y </dev/null
    else
        npx --yes skills add "$REPO_ROOT" --skill "$skill_name" -y </dev/null
    fi
}

symlink_skill_into_target() {
    local skill_name="$1"
    local skill_dir target_root target_path backup_dir backup_path current_target
    skill_dir="$REPO_ROOT/agents/skills/$skill_name"
    [ -f "$skill_dir/SKILL.md" ] || die "Symlink skill mode requires a local checkout with $skill_dir"

    target_root="$(skill_target_root)"
    target_path="$target_root/$skill_name"
    run_cmd mkdir -p "$target_root"

    if [ -L "$target_path" ]; then
        current_target="$(readlink "$target_path" || true)"
        if [ "$current_target" = "$skill_dir" ]; then
            log "Skill '$skill_name' already symlinked at $target_path"
            return 0
        fi
        run_cmd rm "$target_path"
    elif [ -e "$target_path" ]; then
        backup_dir="$target_root/.backup"
        backup_path="$backup_dir/${skill_name}-$(date +%Y%m%d-%H%M%S)"
        run_cmd mkdir -p "$backup_dir"
        run_cmd mv "$target_path" "$backup_path"
        log "Backed up existing skill to $backup_path"
    fi

    log "Symlinking skill '$skill_name' to $skill_dir"
    run_cmd ln -s "$skill_dir" "$target_path"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
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

require_cmd npx

SKILL_LIST_FILE="$(mktemp "${TMPDIR:-/tmp}/share-libs-skills.XXXXXX")"
trap 'rm -f "$SKILL_LIST_FILE"' EXIT
find "$REPO_ROOT/agents/skills" -mindepth 1 -maxdepth 1 -type d -exec test -f '{}/SKILL.md' ';' -print | sort >"$SKILL_LIST_FILE"
[ -s "$SKILL_LIST_FILE" ] || die "No skills found under $REPO_ROOT/agents/skills"

SKILL_COUNT="$(wc -l <"$SKILL_LIST_FILE" | tr -d ' ')"
log "Found $SKILL_COUNT skills under $REPO_ROOT/agents/skills"

while IFS= read -r skill_dir; do
    skill_name="$(basename "$skill_dir")"
    install_skill_via_skills_cli "$skill_name"
    if [ "$SKILL_INSTALL_MODE" = "symlink" ]; then
        symlink_skill_into_target "$skill_name"
    fi
done <"$SKILL_LIST_FILE"

log "Skill bootstrap complete"
