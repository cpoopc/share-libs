#!/bin/bash
# IVA Turn Analyzer - 对话轮次分析
#
# 用法:
#   ./run_turn.sh <session_dir> [--format table|markdown|json] [-o output_file]
#
# 示例:
#   ./run_turn.sh ./output/iva_session/s-xxx-yyy
#   ./run_turn.sh ./output/iva_session/s-xxx-yyy --format markdown
#   ./run_turn.sh ./output/iva_session/s-xxx-yyy -o turn_report.json

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR" || exit 1

# 检查虚拟环境
if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif command -v python3 &> /dev/null; then
    PYTHON="python3"
else
    PYTHON="python"
fi

exec "$PYTHON" -m logtracer_extractors.iva.turn.analyzer "$@"

