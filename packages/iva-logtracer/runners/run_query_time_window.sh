#!/bin/bash
# 按 accountId + 时间窗口查询日志（如 2点25 左右）
# 用法: ./run_query_time_window.sh 37439510 --start "2026-02-26T02:20:00" --end "2026-02-26T02:30:00" [--trace]
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IVA_LOGTRACER_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/env_loader.sh"
extract_env_arg "$@"
load_env "$ENV_NAME" || exit 1
check_env || exit 1
cd "$IVA_LOGTRACER_DIR"
.venv/bin/python scripts/query_account_time_window.py "${REMAINING_ARGS[@]}"
