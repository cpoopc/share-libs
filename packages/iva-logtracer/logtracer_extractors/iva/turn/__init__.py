#!/usr/bin/env python3
"""
IVA Turn Analyzer - 对话轮次分析模块

模块结构:
- models: 数据模型 (Turn, AnalysisReport, etc.)
- patterns: 日志匹配模式
- parser: 日志解析器
- formatters: 报告格式化 (table, markdown, html, mermaid)
- analyzer: 主分析引擎 (VoiceCallAnalyzer)

使用方式:
    from extractors.iva.turn import VoiceCallAnalyzer, AnalysisReport
    from extractors.iva.turn.analyzer import main  # CLI 入口
"""

from .formatters import (
    format_report_markdown,
    format_report_table,
    generate_html_report,
    generate_latency_pie_mermaid,
    generate_sequence_mermaid,
    generate_state_flow_mermaid,
    generate_turn_timeline_mermaid,
    generate_visualizations,
)
from .models import (
    TIMESTAMP_FORMAT,
    TIMESTAMP_FORMAT_NO_MS,
    AnalysisReport,
    CallMetrics,
    CallSession,
    CallState,
    EventType,
    LogEntry,
    Turn,
    TurnAnalysisReport,
    TurnEvent,
    parse_timestamp,
)
from .parser import LogParser
from .patterns import (
    AR_TIMELINE_PATTERNS,
    COMPONENT_TIMELINE_PATTERNS,
    CRITICAL_EVENT_KEYWORDS,
    INTERRUPTION_PATTERNS,
    KEY_EVENT_PATTERNS,
    STATE_PATTERN,
    TURN_END_PATTERNS,
    TURN_START_PATTERNS,
    USER_INPUT_PATTERN,
)


def __getattr__(name: str):
    """延迟导入 analyzer 模块，避免循环导入和运行时警告"""
    if name == "VoiceCallAnalyzer":
        from .analyzer import VoiceCallAnalyzer
        return VoiceCallAnalyzer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # 常量
    "TIMESTAMP_FORMAT",
    "TIMESTAMP_FORMAT_NO_MS",
    # 枚举
    "CallState",
    "EventType",
    # 数据模型
    "LogEntry",
    "CallMetrics",
    "TurnEvent",
    "Turn",
    "CallSession",
    "AnalysisReport",
    "TurnAnalysisReport",
    "parse_timestamp",
    # 模式
    "TURN_START_PATTERNS",
    "TURN_END_PATTERNS",
    "INTERRUPTION_PATTERNS",
    "USER_INPUT_PATTERN",
    "STATE_PATTERN",
    "KEY_EVENT_PATTERNS",
    "CRITICAL_EVENT_KEYWORDS",
    "AR_TIMELINE_PATTERNS",
    "COMPONENT_TIMELINE_PATTERNS",
    # 解析器
    "LogParser",
    # 格式化
    "format_report_table",
    "format_report_markdown",
    "generate_turn_timeline_mermaid",
    "generate_state_flow_mermaid",
    "generate_latency_pie_mermaid",
    "generate_sequence_mermaid",
    "generate_visualizations",
    "generate_html_report",
    # 分析器 (lazy import)
    "VoiceCallAnalyzer",
]

