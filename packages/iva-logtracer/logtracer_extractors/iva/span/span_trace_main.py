#!/usr/bin/env python3
"""
Span Trace Main - Span 追踪主入口

从 IVA 日志中提取和分析 Span 追踪信息

用法:
    python span_trace_main.py s-xxx  # 使用 session_id
    python span_trace_main.py <conversation_id>  # 使用 conversation_id
    python span_trace_main.py --input logs.json  # 从文件读取日志

输出:
    - span_analysis/trace.json - 完整的 Trace JSON
    - span_analysis/timeline.json - 时间线 JSON
    - span_analysis/trace.md - Markdown 报告
    - span_analysis/trace_chrome.json - Chrome Tracing Format
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# 添加路径以支持直接运行
_current_dir = Path(__file__).parent
_extractors_dir = _current_dir.parent.parent
if str(_extractors_dir) not in sys.path:
    sys.path.insert(0, str(_extractors_dir))

try:
    from extractors.iva.orchestrator import SessionTraceOrchestrator
    from extractors.iva.span.span_correlator import correlate_spans
    from extractors.iva.span.span_exporter import export_trace
    from extractors.iva.span.span_extractor import extract_spans_from_logs
    from extractors.iva.trace_context import TraceContext
    from extractors.kibana_client import KibanaClient
except ImportError as e:
    print(f"Import error: {e}", file=sys.stderr)
    print("Please run from the correct directory or check your PYTHONPATH", file=sys.stderr)
    sys.exit(1)


def load_logs_from_file(file_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    """从文件加载日志"""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # 支持两种格式:
    # 1. 直接的组件日志字典: {"assistant_runtime": [...], "nca": [...]}
    # 2. 包含 logs 字段: {"logs": {"assistant_runtime": [...], ...}}
    if "logs" in data:
        return data["logs"]
    return data


def get_default_output_root() -> Path:
    override = os.getenv("IVA_LOGTRACER_OUTPUT_DIR")
    if override:
        return Path(override).expanduser().resolve()

    xdg_cache_home = os.getenv("XDG_CACHE_HOME")
    if xdg_cache_home:
        return Path(xdg_cache_home).expanduser().resolve() / "iva-logtracer" / "output" / "iva_session"
    return Path.home().resolve() / ".cache" / "iva-logtracer" / "output" / "iva_session"


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="IVA Span Trace - 分布式追踪分析",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 从 Kibana 追踪 session
  python span_trace_main.py s-abc123

  # 从本地文件读取
  python span_trace_main.py --input logs.json --conversation-id c7b8b6fe-...
  
  # 指定输出目录
  python span_trace_main.py s-abc123 --output ./my_output
        """
    )
    
    parser.add_argument("id", nargs="?", help="Session ID or Conversation ID")
    parser.add_argument("--input", "-i", type=Path, help="Input log file (JSON)")
    parser.add_argument("--conversation-id", "--conv", help="Conversation ID (if using --input)")
    parser.add_argument("--session-id", "--sess", help="Session ID (optional)")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output directory (default: ~/.cache/iva-logtracer/output/iva_session/.../span_analysis)",
    )
    parser.add_argument("--last", "-l", default="21d", help="Time range for Kibana query")
    parser.add_argument("--formats", "-f", nargs="+", 
                       choices=["json", "timeline", "markdown", "chrome_tracing"],
                       help="Export formats (default: all)")
    
    args = parser.parse_args()
    
    # 确定输入模式
    if args.input:
        # 从文件读取
        if not args.input.exists():
            print(f"❌ Error: Input file not found: {args.input}", file=sys.stderr)
            sys.exit(1)
        
        if not args.conversation_id:
            print("❌ Error: --conversation-id is required when using --input", file=sys.stderr)
            sys.exit(1)
        
        print(f"📂 Loading logs from file: {args.input}")
        logs = load_logs_from_file(args.input)
        conversation_id = args.conversation_id
        session_id = args.session_id
        
    elif args.id:
        # 从 Kibana 查询
        print(f"🔍 Querying Kibana for: {args.id}")
        
        try:
            client = KibanaClient.from_env()
            orchestrator = SessionTraceOrchestrator(client)
            
            # 判断是 session_id 还是 conversation_id
            if args.id.startswith("s-"):
                ctx = TraceContext(session_id=args.id, time_range=args.last)
            else:
                ctx = TraceContext(conversation_id=args.id, time_range=args.last)
            
            ctx = orchestrator.trace(ctx)
            result = ctx.to_result()
            
            logs = result.get("logs", {})
            conversation_id = ctx.conversation_id
            session_id = ctx.session_id
            
            if not conversation_id:
                print("❌ Error: Could not determine conversation_id", file=sys.stderr)
                sys.exit(1)
            
        except Exception as e:
            print(f"❌ Error querying Kibana: {e}", file=sys.stderr)
            sys.exit(1)
    
    else:
        parser.error("Either ID or --input must be provided")
    
    # 提取 Span
    print(f"\n🔬 Extracting spans...")
    spans = extract_spans_from_logs(logs, conversation_id, session_id)
    print(f"   Found {len(spans)} spans")
    
    # 关联 Span
    print(f"🔗 Correlating spans...")
    trace = correlate_spans(spans)
    
    # 统计信息
    root_spans = trace.get_root_spans()
    print(f"   Root spans: {len(root_spans)}")
    
    component_summary = trace.get_component_summary()
    print(f"   Components: {', '.join(component_summary.keys())}")
    
    critical_path = trace.get_critical_path()
    if critical_path:
        total_critical_ms = sum(s.duration_ms or 0 for s in critical_path)
        print(f"   Critical path: {len(critical_path)} spans, {total_critical_ms:.2f}ms")
    
    # 确定输出目录
    if args.output:
        output_dir = args.output
    else:
        from datetime import datetime

        # 生成日期前缀 (YYYYMMDD 格式)
        date_prefix = datetime.now().strftime("%Y%m%d")

        default_output = get_default_output_root()
        safe_session = (session_id or "unknown").replace("/", "_")
        safe_conv = conversation_id.replace("/", "_")
        output_dir = default_output / f"{date_prefix}_{safe_session}-{safe_conv}" / "span_analysis"

    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 导出
    print(f"\n📤 Exporting trace...")
    formats = args.formats or ["json", "timeline", "markdown", "chrome_tracing"]
    saved_files = export_trace(trace, output_dir, formats)
    
    for format_name, file_path in saved_files.items():
        print(f"   ✅ {format_name}: {file_path.name}")
    
    print(f"\n📁 Output directory: {output_dir}")
    
    # 打印关键路径摘要
    if critical_path:
        print(f"\n🎯 Critical Path Summary:")
        for span in critical_path:
            duration = f"{span.duration_ms:.2f}ms" if span.duration_ms else "N/A"
            status_emoji = "✅" if span.status.value == "OK" else "❌"
            print(f"   {status_emoji} [{span.component:20}] {span.name:30} {duration:>10}")


if __name__ == "__main__":
    main()
