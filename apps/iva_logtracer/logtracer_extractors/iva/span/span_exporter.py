#!/usr/bin/env python3
"""
Span Exporter - Span 导出器

支持多种格式导出 Trace:
1. JSON - 结构化数据
2. Timeline JSON - 用于前端时间线可视化
3. Markdown - 人类可读的报告
4. OpenTelemetry Format - 兼容 OTel 工具

导出格式示例:
- Jaeger UI JSON
- Chrome Tracing Format
- Markdown 报告
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .span_model import Span, SpanStatus, Trace
except ImportError:
    from span_model import Span, SpanStatus, Trace


class SpanExporter:
    """Span 导出器基类"""
    
    def export(self, trace: Trace) -> str:
        """导出 Trace"""
        raise NotImplementedError


class JSONExporter(SpanExporter):
    """JSON 格式导出器"""
    
    def export(self, trace: Trace, indent: int = 2) -> str:
        """导出为 JSON"""
        return json.dumps(trace.to_dict(), indent=indent, ensure_ascii=False, default=str)


class TimelineJSONExporter(SpanExporter):
    """
    时间线 JSON 导出器
    
    导出适用于前端时间线可视化的格式
    """
    
    def export(self, trace: Trace) -> str:
        """导出为时间线 JSON"""
        if not trace.start_time:
            base_time = datetime.now()
        else:
            base_time = trace.start_time
        
        timeline_items = []
        
        for span in trace.spans:
            item = {
                "id": span.span_id,
                "parent_id": span.parent_span_id,
                "name": span.name,
                "component": span.component,
                "operation": span.operation,
                "start_ms": span.get_offset_ms(base_time),
                "duration_ms": span.duration_ms or 0,
                "status": span.status.value,
                "attributes": span.attributes,
            }
            timeline_items.append(item)
        
        result = {
            "trace_id": trace.trace_id,
            "session_id": trace.session_id,
            "start_time": base_time.isoformat(),
            "duration_ms": trace.duration_ms,
            "items": timeline_items,
        }
        
        return json.dumps(result, indent=2, ensure_ascii=False)


class MarkdownExporter(SpanExporter):
    """Markdown 格式导出器"""
    
    def export(self, trace: Trace) -> str:
        """导出为 Markdown 报告"""
        lines = []
        
        # 标题
        lines.append(f"# Trace Report: {trace.trace_id}")
        lines.append("")
        lines.append(f"**Session ID**: {trace.session_id}")
        lines.append(f"**Start Time**: {trace.start_time}")
        lines.append(f"**Duration**: {trace.duration_ms:.2f} ms")
        lines.append(f"**Total Spans**: {len(trace.spans)}")
        lines.append("")
        
        # 组件统计
        lines.append("## Component Summary")
        lines.append("")
        component_summary = trace.get_component_summary()
        
        for component, stats in sorted(component_summary.items()):
            lines.append(f"### {component}")
            lines.append(f"- Span Count: {stats['span_count']}")
            lines.append(f"- Total Duration: {stats['total_duration_ms']:.2f} ms")
            lines.append(f"- Avg Duration: {stats['avg_duration_ms']:.2f} ms")
            lines.append(f"- Error Count: {stats['error_count']}")
            lines.append(f"- Operations: {', '.join(stats['operations'])}")
            lines.append("")
        
        # 关键路径
        critical_path = trace.get_critical_path()
        if critical_path:
            lines.append("## Critical Path")
            lines.append("")
            lines.append("The longest execution path:")
            lines.append("")
            
            for i, span in enumerate(critical_path):
                indent = "  " * i
                duration = f"{span.duration_ms:.2f}ms" if span.duration_ms else "N/A"
                lines.append(f"{indent}- [{span.component}] {span.name} ({duration})")
            lines.append("")
        
        # Span 树
        lines.append("## Span Tree")
        lines.append("")
        
        tree = trace.get_span_tree()
        self._render_tree(tree, lines)
        
        # 详细列表
        lines.append("## Span Details")
        lines.append("")
        
        sorted_spans = sorted(trace.spans, key=lambda s: s.start_time or datetime.min)
        for span in sorted_spans:
            self._render_span_detail(span, lines, trace.start_time)
        
        return "\n".join(lines)
    
    def _render_tree(self, tree: List[Dict[str, Any]], lines: List[str], base_level: int = 0):
        """渲染 Span 树"""
        for node in tree:
            span: Span = node['span']
            level = node['level']
            indent = "  " * level
            
            status_emoji = self._get_status_emoji(span.status)
            duration = f"{span.duration_ms:.2f}ms" if span.duration_ms else "N/A"
            
            lines.append(
                f"{indent}- {status_emoji} **{span.name}** "
                f"[{span.component}] ({duration})"
            )
            
            # 递归渲染子节点
            if node['children']:
                self._render_tree(node['children'], lines, level + 1)
    
    def _render_span_detail(self, span: Span, lines: List[str], base_time: Optional[datetime]):
        """渲染单个 Span 的详细信息"""
        status_emoji = self._get_status_emoji(span.status)
        lines.append(f"### {status_emoji} {span.name}")
        lines.append("")
        lines.append(f"- **Span ID**: `{span.span_id}`")
        if span.parent_span_id:
            lines.append(f"- **Parent ID**: `{span.parent_span_id}`")
        lines.append(f"- **Component**: {span.component}")
        lines.append(f"- **Operation**: {span.operation}")
        lines.append(f"- **Kind**: {span.kind.value}")
        
        if base_time and span.start_time:
            offset = span.get_offset_ms(base_time)
            lines.append(f"- **Start Offset**: {offset:.2f} ms")
        
        if span.duration_ms is not None:
            lines.append(f"- **Duration**: {span.duration_ms:.2f} ms")
        
        lines.append(f"- **Status**: {span.status.value}")
        if span.status_message:
            lines.append(f"- **Status Message**: {span.status_message}")
        
        if span.attributes:
            lines.append("- **Attributes**:")
            for key, value in span.attributes.items():
                lines.append(f"  - `{key}`: {value}")
        
        if span.events:
            lines.append("- **Events**:")
            for event in span.events:
                lines.append(f"  - `{event.timestamp.isoformat()}`: {event.name}")
        
        lines.append("")
    
    def _get_status_emoji(self, status: SpanStatus) -> str:
        """获取状态对应的 emoji"""
        return {
            SpanStatus.OK: "✅",
            SpanStatus.ERROR: "❌",
            SpanStatus.CANCELLED: "🚫",
            SpanStatus.UNSET: "⏳",
        }.get(status, "❓")


class ChromeTracingExporter(SpanExporter):
    """
    Chrome Tracing Format 导出器
    
    导出为 Chrome DevTools 支持的追踪格式
    可在 chrome://tracing 中查看
    """
    
    def export(self, trace: Trace) -> str:
        """导出为 Chrome Tracing Format"""
        if not trace.start_time:
            base_time = datetime.now()
        else:
            base_time = trace.start_time
        
        events = []
        
        for span in trace.spans:
            if not span.start_time:
                continue
            
            # 转换为微秒
            start_us = int(span.get_offset_ms(base_time) * 1000)
            duration_us = int((span.duration_ms or 0) * 1000)
            
            # Duration event
            event = {
                "name": span.name,
                "cat": span.component,
                "ph": "X",  # Complete event
                "ts": start_us,
                "dur": duration_us,
                "pid": 1,
                "tid": self._get_thread_id(span.component),
                "args": {
                    "span_id": span.span_id,
                    "operation": span.operation,
                    "status": span.status.value,
                    **span.attributes
                }
            }
            events.append(event)
        
        return json.dumps(events, indent=2)
    
    def _get_thread_id(self, component: str) -> int:
        """为不同组件分配线程 ID"""
        thread_map = {
            "assistant_runtime": 1,
            "nca": 2,
            "aig": 3,
            "gmg": 4,
            "agent_service": 5,
            "cprc_srs": 6,
            "cprc_sgs": 7,
        }
        return thread_map.get(component, 99)


def export_trace(
    trace: Trace,
    output_dir: Path,
    formats: Optional[List[str]] = None
) -> Dict[str, Path]:
    """
    导出 Trace 到多种格式
    
    Args:
        trace: Trace 对象
        output_dir: 输出目录
        formats: 要导出的格式列表，默认全部
    
    Returns:
        格式名称到文件路径的映射
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if formats is None:
        formats = ["json", "timeline", "markdown", "chrome_tracing"]
    
    exporters = {
        "json": JSONExporter(),
        "timeline": TimelineJSONExporter(),
        "markdown": MarkdownExporter(),
        "chrome_tracing": ChromeTracingExporter(),
    }
    
    file_extensions = {
        "json": "trace.json",
        "timeline": "timeline.json",
        "markdown": "trace.md",
        "chrome_tracing": "trace_chrome.json",
    }
    
    saved_files = {}
    
    for format_name in formats:
        if format_name not in exporters:
            continue
        
        exporter = exporters[format_name]
        content = exporter.export(trace)
        
        file_name = file_extensions[format_name]
        file_path = output_dir / file_name
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        saved_files[format_name] = file_path
    
    return saved_files
