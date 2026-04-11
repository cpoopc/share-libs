#!/bin/bash
# Transfer Audit - 只下载关键字段，筛选发生 transfer 的会话，输出用户原话 / 转接目标 / backup 配置
#
# 用法:
#   ./run_transfer_audit.sh 37439510 --env production
#   ./run_transfer_audit.sh 37439510 --env production --last 7d --size 5000

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IVA_LOGTRACER_DIR="$(dirname "$SCRIPT_DIR")"

source "$SCRIPT_DIR/env_loader.sh"
extract_env_arg "$@"
load_env "$ENV_NAME" || exit 1

if [ -z "$KIBANA_URL" ] && [ -z "$KIBANA_ES_URL" ]; then
    echo "❌ Error: KIBANA_URL or KIBANA_ES_URL not set"
    exit 1
fi

cd "$IVA_LOGTRACER_DIR"
.venv/bin/python scripts/transfer_audit.py "${REMAINING_ARGS[@]}"
