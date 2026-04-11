#!/bin/bash
# Window Latency Stats - 按时间窗口聚合关键 turn latency
#
# 用法:
#   ./run_window_latency_stats.sh --env production --account-id 37439510 --start "2026-04-01T00:00:00Z" --end "2026-04-01T01:00:00Z"
#   ./run_window_latency_stats.sh ./output/iva_session/s-xxx-yyy ./output/iva_session/s-aaa-bbb

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IVA_LOGTRACER_DIR="$(dirname "$SCRIPT_DIR")"

source "$SCRIPT_DIR/env_loader.sh"

extract_env_arg "$@"
load_env "$ENV_NAME" || exit 1
check_env || exit 1

cd "$IVA_LOGTRACER_DIR"

.venv/bin/python scripts/window_latency_stats.py "${REMAINING_ARGS[@]}"
