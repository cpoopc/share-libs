#!/usr/bin/env python3
"""
IVA Voice Call Log Analyzer - 报告格式化器

将 AnalysisReport 格式化为不同输出格式 (table, markdown, mermaid)。
"""

import json
from pathlib import Path
from typing import Dict, List, Set

from .models import AnalysisReport, Turn, parse_timestamp

# ============================================================================
# 文本报告格式化
# ============================================================================

def format_report_table(report: AnalysisReport) -> str:
    """格式化报告为表格形式"""
    lines = []

    lines.append("=" * 100)
    lines.append("  IVA Voice Call Analysis Report")
    lines.append("=" * 100)
    lines.append(f"  Session ID:      {report.session_id or 'N/A'}")
    lines.append(f"  Conversation ID: {report.conversation_id or 'N/A'}")
    lines.append(f"  Total Turns:     {report.total_turns}")
    lines.append(f"  Total Duration:  {report.total_duration_ms:.2f} ms")
    lines.append(f"  Avg Turn Duration: {report.avg_turn_duration_ms:.2f} ms")

    # 性能指标
    if report.metrics:
        lines.append("")
        lines.append("  📊 Performance Metrics:")
        if report.metrics.ttft_values:
            lines.append(f"     Avg TTFT:       {report.metrics.avg_ttft_ms:.1f} ms")
            lines.append(f"     TTFT Samples:   {report.metrics.ttft_values}")
        lines.append(f"     LLM Calls:      {report.metrics.llm_call_count}")
        lines.append(f"     LLM Latency:    {report.metrics.llm_total_latency_ms:.0f} ms total, {report.metrics.llm_avg_latency_ms:.0f} ms avg")
        lines.append(f"     Interruptions:  {report.metrics.interruption_count}")
        lines.append(f"     States Visited: {', '.join(sorted(report.metrics.states_visited))}")

    # 终止信息
    if report.is_completed:
        lines.append(f"  ✅ Completed:     {report.termination_reason}")

    # 错误和警告
    if report.errors:
        lines.append("")
        lines.append(f"  🚨 Errors ({len(report.errors)}):")
        for err in report.errors[:5]:  # 只显示前 5 个
            lines.append(f"     - {err[:80]}...")
        if len(report.errors) > 5:
            lines.append(f"     ... and {len(report.errors) - 5} more")

    # Turn 列表
    lines.append("\n" + "-" * 100)
    lines.append("  Turn Details")
    lines.append("-" * 100)

    for turn in report.turns:
        lines.append(f"\n  Turn #{turn.turn_number} ({turn.turn_type})")
        lines.append(f"    Duration: {turn.duration_ms:.2f} ms")
        lines.append(f"    Time: {turn.start_timestamp} ~ {turn.end_timestamp}")

        if turn.user_transcript:
            lines.append(f"    User: \"{turn.user_transcript}\" (conf: {turn.user_transcript_confidence:.2f})")

        if turn.ai_response:
            ai_resp = turn.ai_response[:100].replace("\n", " ")
            lines.append(f"    AI: \"{ai_resp}...\"")

        if turn.llm_calls:
            lines.append(f"    LLM Calls: {len(turn.llm_calls)}")
            for call in turn.llm_calls:
                lines.append(
                    f"      - {call.get('ai_app_name', 'N/A')}/{call.get('model', 'N/A')}: "
                    f"{call.get('request_latency_ms', 0)}ms, {call.get('total_tokens', 0)} tokens"
                )

        if turn.latency_breakdown:
            breakdown = turn.latency_breakdown
            lines.append(f"    Latency Breakdown:")
            lines.append(f"      Total: {breakdown.get('total_ms', 0):.0f}ms")
            if "llm_total_ms" in breakdown:
                lines.append(f"      LLM: {breakdown.get('llm_total_ms', 0):.0f}ms ({breakdown.get('llm_count', 0)} calls)")
                lines.append(f"      Non-LLM: {breakdown.get('non_llm_ms', 0):.0f}ms")

        # Turn 级别的异常
        if turn.anomalies:
            lines.append("    Anomalies:")
            for anomaly in turn.anomalies:
                severity = anomaly.get("severity", "info")
                a_type = anomaly.get("type", "unknown")
                msg = anomaly.get("message", "")
                lines.append(f"      - [{severity}] {a_type}: {msg}")

    # 汇总
    lines.append("\n" + "-" * 100)
    lines.append("  Summary by Turn Type")
    lines.append("-" * 100)

    turn_types: Dict[str, List[Turn]] = {}
    for turn in report.turns:
        if turn.turn_type not in turn_types:
            turn_types[turn.turn_type] = []
        turn_types[turn.turn_type].append(turn)

    for turn_type, turns in turn_types.items():
        avg_duration = sum(t.duration_ms for t in turns) / len(turns) if turns else 0
        total_llm = sum(len(t.llm_calls) for t in turns)
        lines.append(f"  {turn_type}: {len(turns)} turns, avg {avg_duration:.0f}ms, {total_llm} LLM calls")

    lines.append("\n" + "=" * 100)

    return "\n".join(lines)


def format_report_markdown(report: AnalysisReport) -> str:
    """格式化报告为 Markdown"""
    lines = []

    lines.append("# IVA Voice Call Analysis Report")
    lines.append("")
    lines.append(f"- **Session ID:** `{report.session_id or 'N/A'}`")
    lines.append(f"- **Conversation ID:** `{report.conversation_id or 'N/A'}`")
    lines.append(f"- **Total Turns:** {report.total_turns}")
    lines.append(f"- **Total Duration:** {report.total_duration_ms:.2f} ms")
    lines.append(f"- **Avg Turn Duration:** {report.avg_turn_duration_ms:.2f} ms")

    # 性能指标
    if report.metrics:
        lines.append("")
        lines.append("## 📊 Performance Metrics")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        if report.metrics.ttft_values:
            lines.append(f"| Avg TTFT | {report.metrics.avg_ttft_ms:.1f} ms |")
        lines.append(f"| LLM Calls | {report.metrics.llm_call_count} |")
        lines.append(f"| LLM Total Latency | {report.metrics.llm_total_latency_ms:.0f} ms |")
        lines.append(f"| LLM Avg Latency | {report.metrics.llm_avg_latency_ms:.0f} ms |")
        lines.append(f"| Interruptions | {report.metrics.interruption_count} |")
        lines.append(f"| Errors | {report.metrics.error_count} |")
        lines.append(f"| States Visited | {', '.join(sorted(report.metrics.states_visited))} |")

    # 终止信息
    if report.is_completed:
        lines.append("")
        lines.append(f"**Completion Status:** ✅ {report.termination_reason}")

    # 错误和警告
    if report.errors:
        lines.append("")
        lines.append(f"## 🚨 Errors ({len(report.errors)})")
        lines.append("")
        for err in report.errors[:10]:
            lines.append(f"- {err}")
        if len(report.errors) > 10:
            lines.append(f"- ... and {len(report.errors) - 10} more")
    lines.append("")

    # Turn 汇总表
    lines.append("## Turn Summary")
    lines.append("")
    lines.append("| Turn | Type | Duration (ms) | User Input | LLM Calls | TTFT | Anomalies |")
    lines.append("|------|------|---------------|------------|-----------|------|-----------|")

    for turn in report.turns:
        user_input = turn.user_transcript[:30] if turn.user_transcript else "-"
        ttft = f"{turn.ttft_ms}ms" if turn.ttft_ms else "-"

        if turn.anomalies:
            types = [a.get("type", "?") for a in turn.anomalies]
            summary = ", ".join(types[:2])
            if len(types) > 2:
                summary += f" (+{len(types) - 2} more)"
        else:
            summary = "-"

        lines.append(
            f"| {turn.turn_number} | {turn.turn_type} | {turn.duration_ms:.0f} | "
            f"{user_input} | {len(turn.llm_calls)} | {ttft} | {summary} |"
        )

    # Turn 详情
    lines.append("")
    lines.append("## Turn Details")

    for turn in report.turns:
        lines.append("")
        interrupted = " ⚠️ (interrupted)" if turn.was_interrupted else ""
        lines.append(f"### Turn {turn.turn_number}: {turn.turn_type}{interrupted}")
        lines.append("")
        lines.append(f"- **Duration:** {turn.duration_ms:.2f} ms")
        lines.append(f"- **Time:** `{turn.start_timestamp}` ~ `{turn.end_timestamp}`")
        if turn.states:
            lines.append(f"- **States:** {' → '.join(turn.states)}")
        if turn.ttft_ms:
            lines.append(f"- **TTFT:** {turn.ttft_ms} ms")

        if turn.user_transcript:
            lines.append(f"- **User:** \"{turn.user_transcript}\" (confidence: {turn.user_transcript_confidence:.2f})")

        if turn.ai_response:
            ai_resp = turn.ai_response[:150].replace("\n", " ")
            lines.append(f"- **AI Response:** \"{ai_resp}...\"")

        # Turn 级别的异常
        if turn.anomalies:
            lines.append("")
            lines.append("**Anomalies:**")
            for anomaly in turn.anomalies:
                severity = anomaly.get("severity", "info")
                a_type = anomaly.get("type", "unknown")
                msg = anomaly.get("message", "")
                lines.append(f"- `[{severity}] {a_type}`: {msg}")

        if turn.llm_calls:
            lines.append("")
            lines.append("**LLM Calls:**")
            lines.append("")
            lines.append("| App | Model | Latency (ms) | Tokens |")
            lines.append("|-----|-------|--------------|--------|")
            for call in turn.llm_calls:
                lines.append(
                    f"| {call.get('ai_app_name', 'N/A')} | {call.get('model', 'N/A')} | "
                    f"{call.get('request_latency_ms', 0)} | {call.get('total_tokens', 0)} |"
                )

        if turn.tool_calls:
            lines.append("")
            lines.append("**Tool Calls (component view):**")
            lines.append("")
            lines.append("| Tool | Type | Component | Status | Duration (ms) |")
            lines.append("|------|------|-----------|--------|---------------|")
            for call in turn.tool_calls:
                duration = call.get("duration_ms")
                duration_str = f"{duration:.0f}" if duration is not None else "-"
                lines.append(
                    f"| {call.get('tool_name', 'N/A')} | {call.get('tool_type', 'unknown')} | "
                    f"{call.get('source_component', 'N/A')} | {call.get('status', 'unknown')} | "
                    f"{duration_str} |"
                )

    return "\n".join(lines)


# ============================================================================
# Mermaid 可视化
# ============================================================================

def generate_turn_timeline_mermaid(report: AnalysisReport) -> str:
    """生成 Turn 时间线 Mermaid 图"""
    lines = ["gantt"]
    lines.append("    title Voice Call Turn Timeline")
    lines.append("    dateFormat X")
    lines.append("    axisFormat %s")
    lines.append("")

    if not report.turns:
        return "\n".join(lines)

    # 计算基准时间
    first_turn = report.turns[0]
    base_ts = parse_timestamp(first_turn.start_timestamp)
    if not base_ts:
        return "\n".join(lines)

    for turn in report.turns:
        start_ts = parse_timestamp(turn.start_timestamp)
        end_ts = parse_timestamp(turn.end_timestamp)
        if not start_ts or not end_ts:
            continue

        start_ms = int((start_ts - base_ts).total_seconds() * 1000)
        duration_ms = int(turn.duration_ms)

        # 确定颜色/状态
        status = "active" if "interrupted" in turn.turn_type else "done"
        label = f"Turn {turn.turn_number}: {turn.turn_type}"
        if turn.user_transcript:
            label += f" ({turn.user_transcript[:15]}...)" if len(turn.user_transcript) > 15 else f" ({turn.user_transcript})"

        lines.append(f"    section Turn {turn.turn_number}")
        lines.append(f"    {label} :{status}, {start_ms}, {duration_ms}ms")

    return "\n".join(lines)


def generate_state_flow_mermaid(report: AnalysisReport) -> str:
    """生成状态机流转 Mermaid 图"""
    lines = ["stateDiagram-v2"]
    lines.append("    direction LR")

    if not report.metrics or not report.metrics.states_visited:
        return "\n".join(lines)

    # 收集所有状态转换
    transitions = []
    for turn in report.turns:
        if turn.states and len(turn.states) > 1:
            for i in range(len(turn.states) - 1):
                transitions.append((turn.states[i], turn.states[i + 1]))

    # 去重并生成
    seen = set()
    for from_state, to_state in transitions:
        key = f"{from_state}->{to_state}"
        if key not in seen:
            seen.add(key)
            lines.append(f"    {from_state} --> {to_state}")

    return "\n".join(lines)


def generate_latency_pie_mermaid(report: AnalysisReport) -> str:
    """生成延迟分布饼图 Mermaid"""
    lines = ["pie showData"]
    lines.append('    title "Turn Duration Distribution"')

    for turn in report.turns:
        label = f"Turn {turn.turn_number} ({turn.turn_type})"
        lines.append(f'    "{label}" : {turn.duration_ms:.0f}')

    return "\n".join(lines)


def generate_sequence_mermaid(report: AnalysisReport) -> str:
    """生成多组件对话时序图 Mermaid（基于 component_timeline）"""

    lines = ["sequenceDiagram"]
    lines.append("    participant U as User")
    lines.append("    participant AR as Assistant Runtime")
    lines.append("    participant NCA as NCA")
    lines.append("    participant AIG as AIG")
    lines.append("    participant GMG as GMG")
    lines.append("    participant AS as AgentService")
    lines.append("")

    # 将 component_timeline 中的组件名映射到时序图 participant
    component_to_participant = {
        "FSM": "AR", "STT": "AR", "Agent": "AR", "Runtime": "AR", "TTS": "AR", "Tool": "AR", "AR": "AR",
        "GMG": "GMG", "gmg": "GMG",
        "agent_service": "AS", "nca": "NCA", "aig": "AIG",
        "assistant_runtime": "AR",
    }

    for turn in report.turns:
        lines.append(f"    %% Turn {turn.turn_number}")
        lines.append(f"    Note over AR: Turn {turn.turn_number} ({turn.turn_type})")

        if turn.turn_type == "greeting":
            lines.append("    AR->>U: [Greeting]")
        else:
            if turn.user_transcript:
                transcript = turn.user_transcript
                if len(transcript) > 30:
                    transcript = transcript[:30] + "..."
                transcript = transcript.replace("\n", " ").replace('"', "'")
                lines.append(f'    U->>AR: "{transcript}"')

        hidden_logs_per_component: Dict[str, int] = {}
        seen_notes: Set[str] = set()

        for ev in turn.component_timeline or []:
            comp = ev.get("component")
            participant = component_to_participant.get(comp)
            if not participant:
                continue

            event = ev.get("event", "") or "event"
            detail = ev.get("detail", "") or ""

            if event == "log":
                hidden_logs_per_component[participant] = hidden_logs_per_component.get(participant, 0) + 1
                continue

            msg = event
            if detail:
                msg = f"{event}: {detail}"
            msg = msg.replace("\n", " ").replace('"', "'")
            if len(msg) > 60:
                msg = msg[:60] + "..."

            note_line = f"    Note over {participant}: {msg}"
            if note_line in seen_notes:
                continue
            seen_notes.add(note_line)
            lines.append(note_line)

        for participant, count in hidden_logs_per_component.items():
            lines.append(f"    Note over {participant}: ({count} internal log events hidden)")

        if turn.ai_response:
            ai_resp = turn.ai_response
            if len(ai_resp) > 30:
                ai_resp = ai_resp[:30] + "..."
            ai_resp = ai_resp.replace("\n", " ").replace('"', "'")
            lines.append(f'    AR->>U: "{ai_resp}"')

        if turn.was_interrupted:
            lines.append("    U--xAR: [Interrupted]")

        lines.append("")

    return "\n".join(lines)


def generate_visualizations(report: AnalysisReport, output_dir: Path) -> Dict[str, str]:
    """生成所有可视化文件"""
    visualizations = {}

    # Turn Timeline
    timeline = generate_turn_timeline_mermaid(report)
    timeline_path = output_dir / "turn_timeline.mmd"
    with open(timeline_path, "w", encoding="utf-8") as f:
        f.write(timeline)
    visualizations["timeline"] = str(timeline_path)

    # State Flow
    state_flow = generate_state_flow_mermaid(report)
    state_flow_path = output_dir / "state_flow.mmd"
    with open(state_flow_path, "w", encoding="utf-8") as f:
        f.write(state_flow)
    visualizations["state_flow"] = str(state_flow_path)

    # Latency Pie
    pie = generate_latency_pie_mermaid(report)
    pie_path = output_dir / "latency_pie.mmd"
    with open(pie_path, "w", encoding="utf-8") as f:
        f.write(pie)
    visualizations["latency_pie"] = str(pie_path)

    # Sequence Diagram
    sequence = generate_sequence_mermaid(report)
    sequence_path = output_dir / "sequence.mmd"
    with open(sequence_path, "w", encoding="utf-8") as f:
        f.write(sequence)
    visualizations["sequence"] = str(sequence_path)

    return visualizations


def generate_html_report(report: AnalysisReport, output_path: Path) -> None:
    """生成 HTML 可视化报告"""
    from cptools_web import TimelineRenderer, TreeTimelineRenderer

    from .timeline_converter import convert_turn_to_tree

    # 查找模板文件
    # __file__ = extractors/iva/turn/formatters.py
    # 模板在: templates/turn_report.html (从 iva-logtracer 根目录)
    iva_logtracer_root = Path(__file__).parent.parent.parent.parent
    template_paths = [
        iva_logtracer_root / "templates" / "turn_report.html",
        Path(__file__).parent.parent.parent / "templates" / "turn_report.html",
        Path(__file__).parent / "templates" / "turn_report.html",
    ]

    template_content = None
    for tp in template_paths:
        if tp.exists():
            with open(tp, "r", encoding="utf-8") as f:
                template_content = f.read()
            break

    if not template_content:
        # 使用内联模板
        template_content = """<!DOCTYPE html>
<html><head><title>Turn Report</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
</head><body>
<h1>IVA Voice Call Analysis Report</h1>
<pre>__REPORT_DATA__</pre>
<script>const REPORT_DATA = __REPORT_DATA__; console.log(REPORT_DATA);</script>
</body></html>"""

    # 使用 cptools-web-libs-timeline 包获取 CSS/JS
    timeline_renderer = TimelineRenderer()
    tree_renderer = TreeTimelineRenderer()

    timeline_js = timeline_renderer.get_js_content()
    timeline_css = timeline_renderer.get_css_content()
    tree_timeline_js = tree_renderer.get_js_content()
    tree_timeline_css = tree_renderer.get_css_content()

    # 生成树形时间线数据 (每个 Turn 一个树)
    tree_timeline_data = []
    for turn in report.turns:
        # 为每个 Turn 生成独立的树，时间从 0 开始
        turn_tree = convert_turn_to_tree(turn)
        if turn_tree:
            tree_timeline_data.append(turn_tree)

    # 注入数据
    def safe_json_dump(obj):
        """Dump JSON safely for embedding in HTML script tags"""
        # Compact JSON
        json_str = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
        # Escape characters that are unsafe in HTML script tags or JS strings
        json_str = json_str.replace('<', '\\u003c')
        json_str = json_str.replace('>', '\\u003e')
        # JSON spec allows these, but JS string literals treat them as newlines
        json_str = json_str.replace('\u2028', '\\u2028')
        json_str = json_str.replace('\u2029', '\\u2029')
        return json_str

    report_json = safe_json_dump(report.to_dict())
    tree_timeline_json = safe_json_dump(tree_timeline_data)

    html_content = template_content.replace("__REPORT_DATA__", report_json)
    html_content = html_content.replace("/* __TIMELINE_RENDERER_CSS__ */", timeline_css)
    html_content = html_content.replace("// __TIMELINE_RENDERER_JS__", timeline_js)
    html_content = html_content.replace("/* __TREE_TIMELINE_CSS__ */", tree_timeline_css)
    html_content = html_content.replace("// __TREE_TIMELINE_JS__", tree_timeline_js)
    html_content = html_content.replace("__TREE_TIMELINE_DATA__", tree_timeline_json)

    # 写入文件
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)


def generate_tree_timeline_html(report: AnalysisReport, output_dir: Path) -> List[str]:
    """
    生成树形时间线HTML可视化
    
    Args:
        report: 分析报告
        output_dir: 输出目录
        
    Returns:
        生成的HTML文件路径列表
    """
    try:
        from .timeline_renderer import generate_timeline_html
        
        # 创建timelines子目录
        timeline_dir = output_dir / 'timelines'
        timeline_dir.mkdir(exist_ok=True, parents=True)
        
        # 生成时间线HTML文件
        timeline_files = generate_timeline_html(
            report.turns,
            timeline_dir,
            session_id=report.session_id,
            conversation_id=report.conversation_id
        )
        
        print(f"✅ Generated {len(timeline_files)} tree-timeline HTML files:")
        for tf in timeline_files:
            print(f"   - {Path(tf).name}")
        
        return timeline_files
        
    except ImportError as e:
        print(f"⚠️  Tree-timeline renderer not available: {e}")
        print("   Install jinja2 to enable tree-timeline visualization")
        return []
    except Exception as e:
        print(f"⚠️  Failed to generate tree-timeline HTML: {e}")
        import traceback
        traceback.print_exc()
        return []

