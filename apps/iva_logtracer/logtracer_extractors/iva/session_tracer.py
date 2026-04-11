#!/usr/bin/env python3
"""
IVA Session Trace - IVA 跨组件日志追踪

根据 sessionId 追踪 IVA 多个组件的日志:
1. 从 air_assistant_runtime 日志中提取 conversationId
2. 使用 conversationId 搜索多个组件的日志
3. 提取 srs/sgs_session_id 搜索 CPRC 日志

插件化架构:
- TraceContext: 共享上下文
- LogLoader: 日志加载器插件接口
- SessionTraceOrchestrator: 编排器
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

try:
    from ..kibana_client import KibanaClient
    from .ai_extractor import save_ai_analysis_files
    from .loaders import DEFAULT_CONVERSATION_LOADERS, DEFAULT_SESSION_LOADERS
    from .orchestrator import SessionTraceOrchestrator
    from .trace_context import TraceContext
except ImportError:
    # 直接运行时，添加正确的 path
    _current_dir = Path(__file__).parent
    _extractors_dir = _current_dir.parent
    _kibana_dir = _extractors_dir.parent
    if str(_kibana_dir) not in sys.path:
        sys.path.insert(0, str(_kibana_dir))

    from extractors.iva.ai_extractor import save_ai_analysis_files
    from extractors.iva.loaders import DEFAULT_CONVERSATION_LOADERS, DEFAULT_SESSION_LOADERS
    from extractors.iva.orchestrator import SessionTraceOrchestrator
    from extractors.iva.trace_context import TraceContext
    from extractors.kibana_client import KibanaClient


# 默认输出目录
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent / "output" / "iva_session"


def get_output_dir(session_id: str, conversation_id: str) -> Path:
    """获取输出目录: output/iva_session/{YYYYMMDD}_{sessionId}-{conversationId}"""
    from datetime import datetime

    # 生成日期前缀 (YYYYMMDD 格式)
    date_prefix = datetime.now().strftime("%Y%m%d")

    safe_session = session_id.replace("/", "_").replace("\\", "_")
    safe_conversation = conversation_id.replace("/", "_").replace("\\", "_")
    output_dir = DEFAULT_OUTPUT_DIR / f"{date_prefix}_{safe_session}-{safe_conversation}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def format_logs_plain(logs: Dict[str, List[Dict]]) -> str:
    """格式化日志为纯文本，按时间排序"""
    all_logs = []
    for component, component_logs in logs.items():
        for log in component_logs:
            all_logs.append({
                "component": component,
                "timestamp": log.get("@timestamp", ""),
                "message": log.get("message", ""),
            })
    all_logs.sort(key=lambda x: x["timestamp"])
    lines = [f"[{log['timestamp']}] [{log['component']}] {log['message']}" for log in all_logs]
    return "\n".join(lines)


def format_logs_table(logs: Dict[str, List[Dict]], max_msg_width: int = 200) -> str:
    """格式化日志为表格形式"""
    lines = []
    for component, component_logs in logs.items():
        lines.append(f"\n{'='*100}")
        lines.append(f"  [{component.upper()}] - {len(component_logs)} logs")
        lines.append("-" * 100)
        if not component_logs:
            lines.append("  (no logs)")
            continue
        for log in component_logs:
            timestamp = log.get("@timestamp", "")[:23]
            level = log.get("level", "INFO")[:5]
            message = log.get("message", "")[:max_msg_width]
            logger = log.get("logger", "")[:20]
            lines.append(f"  {timestamp} [{level:5}] {logger:20} | {message}")
    return "\n".join(lines)


def is_session_id(id_str: str) -> bool:
    """判断是否为 sessionId (以 's-' 开头)"""
    return id_str.startswith("s-")


def is_conversation_id(id_str: str) -> bool:
    """判断是否为 conversationId (UUID 格式)"""
    uuid_pattern = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    return bool(re.match(uuid_pattern, id_str))


def main():
    """IVA Session Trace 主入口"""
    parser = argparse.ArgumentParser(
        description="IVA Session Trace - IVA 跨组件日志追踪",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python session_tracer.py s-abc123
  python session_tracer.py s-abc123 --last 24h
  python session_tracer.py s-abc123 --loaders assistant_runtime nca cprc_srs

可用的加载器:
  assistant_runtime - Assistant Runtime 日志
  agent_service     - Agent Service 日志
  nca               - NCA 日志
  cprc_srs          - CPRC SRS (语音识别) 日志
  cprc_sgs          - CPRC SGS (语音合成) 日志
        """
    )
    parser.add_argument("id", help="Session ID (s-xxx) or Conversation ID (UUID)")
    parser.add_argument("--last", "-l", default="21d", help="Time range (default: 21d)")
    parser.add_argument("--loaders", "-L", nargs="+", help="Loaders to use")
    parser.add_argument("--components", "-c", nargs="+", dest="loaders_alias", help="Alias for --loaders (deprecated)")
    parser.add_argument("--size", "-n", type=int, default=10000, help="Max logs per component")
    parser.add_argument("--format", "-f", choices=["table", "json"], default="json", help="Output format")
    parser.add_argument("--output", "-o", help="Output file")
    parser.add_argument("--no-save", action="store_true", help="Don't auto-save")
    parser.add_argument("--save-json", action="store_true", help="Also save trace JSON files")

    args = parser.parse_args()
    enabled_loaders = set(args.loaders or args.loaders_alias or [])
    input_id = args.id
    use_conversation_id = False

    if is_session_id(input_id):
        print(f"🔖 Detected sessionId: {input_id}")
        if not enabled_loaders:
            enabled_loaders = set(DEFAULT_SESSION_LOADERS)
    elif is_conversation_id(input_id):
        print(f"🔖 Detected conversationId (UUID): {input_id}")
        use_conversation_id = True
        if not enabled_loaders:
            enabled_loaders = set(DEFAULT_CONVERSATION_LOADERS)
    else:
        parser.error(f"Unknown ID format: {input_id}")

    try:
        client = KibanaClient.from_env()
        orchestrator = SessionTraceOrchestrator(client)

        if use_conversation_id:
            # 使用智能回退的 conversation trace
            ctx = orchestrator.trace_by_conversation(
                conversation_id=input_id,
                time_range=args.last,
                enabled_loaders=enabled_loaders,
                size=args.size,
            )
        else:
            # Session trace
            ctx = orchestrator.trace_by_session(
                session_id=input_id,
                time_range=args.last,
                enabled_loaders=enabled_loaders,
                size=args.size,
            )

        result = ctx.to_result()
        session_id = ctx.session_id or "unknown"
        conversation_id = ctx.conversation_id

        if not conversation_id:
            print("\n❌ Cannot save: conversationId not found")
            sys.exit(1)

        # 格式化输出
        if args.format == "json":
            output = json.dumps(result, indent=2, ensure_ascii=False, default=str)
        else:
            output = format_logs_table(result["logs"])

        # 输出处理
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"\n✅ Output saved to: {output_path}")
        elif not args.no_save:
            output_dir = get_output_dir(session_id, conversation_id)
            logs = result.get("logs", {})

            for component, component_logs in logs.items():
                if not component_logs:
                    continue
                if args.save_json:
                    json_path = output_dir / f"{component}_trace.json"
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(component_logs, f, indent=2, ensure_ascii=False, default=str)
                    print(f"✅ {component}_trace.json")

                log_path = output_dir / f"{component}_message.log"
                lines = [f"[{log.get('@timestamp', '')}] {log.get('message', '')}"
                         for log in sorted(component_logs, key=lambda x: x.get("@timestamp", ""))]
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))

            combine_path = output_dir / "combine.log"
            plain_text = format_logs_plain(logs)
            with open(combine_path, "w", encoding="utf-8") as f:
                f.write(plain_text)
            print(f"✅ combine.log: {len(plain_text.splitlines())} lines")

            summary_path = output_dir / "summary.json"
            summary = {
                "session_id": ctx.session_id,
                "conversation_id": ctx.conversation_id,
                "srs_session_id": ctx.srs_session_id,
                "sgs_session_id": ctx.sgs_session_id,
                "summary": ctx.get_summary(),
            }
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)

            # 生成 AI 分析文件
            print("\n🤖 Generating AI analysis files...")
            try:
                ai_files = save_ai_analysis_files(output_dir, logs, summary)
                for name, path in ai_files.items():
                    print(f"   ✅ ai_analysis/{name}")
            except Exception as e:
                print(f"   ⚠️  AI analysis generation failed: {e}", file=sys.stderr)

            print(f"\n📁 Output directory: {output_dir}")
        else:
            print(output)

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

