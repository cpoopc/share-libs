#!/bin/bash
# Session Trace - 跨组件日志追踪
#
# 使用方法:
#   ./run_trace.sh <sessionId>                        # 追踪 session
#   ./run_trace.sh <sessionId> --env lab              # 使用 lab 环境
#   ./run_trace.sh <sessionId> --last 24h             # 指定时间范围
#   ./run_trace.sh <sessionId> -o ./trace_result.json # 导出到文件

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IVA_LOGTRACER_DIR="$(dirname "$SCRIPT_DIR")"

# 加载环境工具
source "$SCRIPT_DIR/env_loader.sh"

# 提取 --env 参数
extract_env_arg "$@"

# 加载环境配置
load_env "$ENV_NAME" || exit 1

# 检查必需的环境变量
check_env || exit 1

# 切换到项目目录
cd "$IVA_LOGTRACER_DIR"

# 显示帮助
show_help() {
    echo "Session Trace - 跨组件日志追踪 (插件化架构)"
    echo ""
    echo "功能:"
    echo "  1. 根据 sessionId 从 assistant_runtime 提取 conversationId"
    echo "  2. 使用 conversationId 搜索 agent_service 和 nca 的日志"
    echo "  3. 从 assistant_runtime 提取 srs/sgs_session_id 搜索 cprc 日志"
    echo "  4. 自动保存到 output/session/{YYYYMMDD}_{sessionId}-{conversationId}/"
    echo ""
    echo "使用方法:"
    echo "  ./run_trace.sh <sessionId>                          # 追踪并保存"
    echo "  ./run_trace.sh <sessionId> --last 24h               # 指定时间范围"
    echo "  ./run_trace.sh <sessionId> -L assistant_runtime nca # 指定加载器"
    echo "  ./run_trace.sh <sessionId> --format table           # 表格输出"
    echo "  ./run_trace.sh <sessionId> --no-save                # 不自动保存"
    echo "  ./run_trace.sh <sessionId> -o ./result.json         # 指定输出文件"
    echo ""
    echo "可用的加载器 (Loaders):"
    echo "  assistant_runtime  从 assistant_runtime 日志开始追踪"
    echo "  agent_service      依赖 conversation_id"
    echo "  nca                依赖 conversation_id"
    echo "  cprc_srs           依赖 srs_session_id (语音识别)"
    echo "  cprc_sgs           依赖 sgs_session_id (语音合成)"
    echo ""
    echo "选项:"
    echo "  --last, -l         时间范围 (默认 21d)"
    echo "  --env, -e          环境名称 (lab, production 等)"
    echo "  --loaders, -L      加载器列表 (新参数，推荐使用)"
    echo "  --components, -c   加载器列表 (旧参数别名，已废弃)"
    echo "  --size, -n         每组件最大日志数 (默认 10000)"
    echo "  --format, -f       输出格式 (table, json) (默认 json)"
    echo "  --output, -o       输出文件 (默认 自动保存)"
    echo "  --no-save          不自动保存到 output 目录"
    echo "  --save-json        同时保存 trace JSON 文件"
}

# 解析参数
if [ ${#REMAINING_ARGS[@]} -eq 0 ]; then
    show_help
    exit 0
fi

case ${REMAINING_ARGS[0]} in
    --help|-h)
        show_help
        exit 0
        ;;
    *)
        echo "🔍 IVA Session Trace"
        echo ""
        .venv/bin/python -m logtracer_extractors.iva.session_tracer "${REMAINING_ARGS[@]}"
        ;;
esac
