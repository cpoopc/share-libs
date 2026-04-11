#!/bin/bash
# 查询最近 N 天 accountId + assistantId 且含 transfer 的会话，保存到新目录并执行 trace + AI 分析
#
# 用法:
#   ./run_query_account_assistant_transfer.sh 37439510 e2260bba-dba7-42b1-abd5-8fc02c88e5cf --env production
#   ./run_query_account_assistant_transfer.sh 37439510 e2260bba-dba7-42b1-abd5-8fc02c88e5cf --env production --last 7d -o ./my_audit

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
.venv/bin/python scripts/query_account_assistant_transfer.py "${REMAINING_ARGS[@]}"
