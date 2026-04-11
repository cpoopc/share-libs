#!/bin/bash
# 通用环境加载脚本
# 支持多环境配置: .env.lab, .env.production 等
#
# 用法:
#   source env_loader.sh           # 使用默认 .env
#   source env_loader.sh lab       # 使用 .env.lab
#   source env_loader.sh production # 使用 .env.production

# 获取脚本所在目录
if [ -z "$IVA_LOGTRACER_DIR" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    IVA_LOGTRACER_DIR="$(dirname "$SCRIPT_DIR")"
fi

# 解析环境参数
load_env() {
    local env_name="$1"
    local env_file

    if [ -n "$env_name" ]; then
        env_file="$IVA_LOGTRACER_DIR/.env.$env_name"
        if [ ! -f "$env_file" ]; then
            echo "❌ Error: Environment file not found: $env_file"
            echo "   Available environments:"
            for f in "$IVA_LOGTRACER_DIR"/.env.*; do
                if [ -f "$f" ] && [[ "$f" != *.example ]]; then
                    basename "$f" | sed 's/^\.env\./   - /'
                fi
            done
            return 1
        fi
    else
        # No --env specified, check if .env exists, otherwise show help
        env_file="$IVA_LOGTRACER_DIR/.env"
        if [ ! -f "$env_file" ]; then
            echo "❌ Error: No default .env file found. Please specify an environment with --env"
            echo ""
            echo "   Usage: ./run_trace.sh <sessionId> --env <environment>"
            echo ""
            echo "   Available environments:"
            for f in "$IVA_LOGTRACER_DIR"/.env.*; do
                if [ -f "$f" ] && [[ "$f" != *.example ]]; then
                    basename "$f" | sed 's/^\.env\./   - /'
                fi
            done
            echo ""
            echo "   Example: ./run_trace.sh s-abc123 --env production"
            return 1
        fi
    fi

    if [ -f "$env_file" ]; then
        set -a
        source "$env_file"
        set +a

        # 显示当前环境
        if [ -n "$env_name" ]; then
            echo "🌍 Environment: $env_name"
        else
            echo "🌍 Environment: default"
        fi
        echo "   URL: $KIBANA_URL"
        echo ""
    fi
}

# 从参数中提取 --env 选项
extract_env_arg() {
    local args=()
    ENV_NAME=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --env|-e)
                ENV_NAME="$2"
                shift 2
                ;;
            --env=*)
                ENV_NAME="${1#*=}"
                shift
                ;;
            *)
                args+=("$1")
                shift
                ;;
        esac
    done
    
    # 返回剩余参数
    REMAINING_ARGS=("${args[@]}")
}

# 检查必需的环境变量
check_env() {
    if [ -z "$KIBANA_URL" ] && [ -z "$KIBANA_ES_URL" ]; then
        echo "❌ Error: KIBANA_URL or KIBANA_ES_URL not set"
        return 1
    fi
}
