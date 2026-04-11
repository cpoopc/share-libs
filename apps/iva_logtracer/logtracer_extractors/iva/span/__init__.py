#!/usr/bin/env python3
"""
Span Tracing - IVA 分布式追踪系统

提供类似 OpenTelemetry 的 Span 追踪能力：
- 从日志中提取 Span
- 建立 Span 之间的父子关系
- 生成追踪可视化

主要模块:
- span_model: Span 数据模型
- span_extractor: Span 提取器
- span_correlator: Span 关联器
- span_exporter: Span 导出器

使用示例:
    from extractors.iva.span import extract_spans_from_logs, correlate_spans, export_trace
    
    # 1. 提取 Span
    spans = extract_spans_from_logs(logs, conversation_id)
    
    # 2. 关联 Span (建立父子关系)
    trace = correlate_spans(spans)
    
    # 3. 导出
    export_trace(trace, output_dir)
"""

from .span_correlator import (
    SpanCorrelator,
    correlate_spans,
)
from .span_exporter import (
    ChromeTracingExporter,
    JSONExporter,
    MarkdownExporter,
    SpanExporter,
    TimelineJSONExporter,
    export_trace,
)
from .span_extractor import (
    SpanExtractor,
    extract_spans_from_logs,
)
from .span_model import (
    Span,
    SpanEvent,
    SpanKind,
    SpanStatus,
    Trace,
)

__all__ = [
    # Models
    "Span",
    "SpanEvent",
    "SpanKind",
    "SpanStatus",
    "Trace",
    
    # Extractors
    "SpanExtractor",
    "extract_spans_from_logs",
    
    # Correlators
    "SpanCorrelator",
    "correlate_spans",
    
    # Exporters
    "SpanExporter",
    "JSONExporter",
    "TimelineJSONExporter",
    "MarkdownExporter",
    "ChromeTracingExporter",
    "export_trace",
]
