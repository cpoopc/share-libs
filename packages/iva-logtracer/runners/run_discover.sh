#!/bin/bash
# Discovery runner - 根据业务实体发现 IVA session 列表

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IVA_LOGTRACER_DIR="$(dirname "$SCRIPT_DIR")"

source "$SCRIPT_DIR/env_loader.sh"

extract_env_arg "$@"
load_env "$ENV_NAME" || exit 1
check_env || exit 1

cd "$IVA_LOGTRACER_DIR"

CLI_ARGS=("discover")
if [ -n "$ENV_NAME" ]; then
    CLI_ARGS+=("--env" "$ENV_NAME")
fi
CLI_ARGS+=("${REMAINING_ARGS[@]}")

.venv/bin/python -m logtracer_extractors.cli "${CLI_ARGS[@]}"
