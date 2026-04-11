#!/usr/bin/env python3
"""
Jaeger UI JSON 导出器

导出为 Jaeger UI 支持的 JSON 格式
可以通过 Jaeger UI 的 JSON 文件上传功能查看

格式参考: https://www.jaegertracing.io/docs/1.22/apis/#json-format
"""

import hashlib
import json
from typing import Any, Dict

try:
    from .span_model import Span, SpanStatus, Trace
except ImportError:
    from span_model import Span, SpanStatus, Trace


class JaegerExporter:
    """Jaeger UI JSON 导出器"""
    
    def export(self, trace: Trace) -> str:
        """导出为 Jaeger UI JSON 格式"""
        # 收集所有进程 (组件)
        processes = {}
        process_id_map = {}
        
        for span in trace.spans:
            if span.component not in process_id_map:
                pid = f"p{len(process_id_map) + 1}"
                process_id_map[span.component] = pid
                processes[pid] = {
                    "serviceName": span.component,
                    "tags": [{"key": "component", "type": "string", "value": span.component}]
                }
        
        # 转换 spans
        jaeger_spans = []
        for span in trace.spans:
            if not span.start_time:
                continue
            
            start_time_us = int(span.start_time.timestamp() * 1_000_000)
            duration_us = max(0, int((span.duration_ms or 0) * 1000))
            
            # 构建 references (父子关系)
            references = []
            if span.parent_span_id:
                references.append({
                    "refType": "CHILD_OF",
                    "traceID": self._to_hex_id(span.trace_id),
                    "spanID": self._to_hex_id(span.parent_span_id)
                })
            
            # 构建 tags
            tags = [
                {"key": "component", "type": "string", "value": span.component},
                {"key": "operation", "type": "string", "value": span.operation},
                {"key": "status", "type": "string", "value": span.status.value},
                {"key": "span.kind", "type": "string", "value": span.kind.value},
            ]
            
            # 添加自定义 attributes
            for key, value in span.attributes.items():
                tag_type = "string"
                if isinstance(value, bool):
                    tag_type = "bool"
                elif isinstance(value, int):
                    tag_type = "int64"
                elif isinstance(value, float):
                    tag_type = "float64"
                tags.append({
                    "key": key,
                    "type": tag_type,
                    "value": str(value) if tag_type == "string" else value
                })
            
            # 如果有错误状态，添加 error tag
            if span.status == SpanStatus.ERROR:
                tags.append({"key": "error", "type": "bool", "value": True})
                if span.status_message:
                    tags.append({"key": "error.message", "type": "string", "value": span.status_message})
            
            # 构建 logs (从 span events)
            logs = []
            for event in span.events:
                log_fields = [{"key": "event", "type": "string", "value": event.name}]
                for key, value in event.attributes.items():
                    log_fields.append({"key": key, "type": "string", "value": str(value)})
                logs.append({
                    "timestamp": int(event.timestamp.timestamp() * 1_000_000),
                    "fields": log_fields
                })
            
            jaeger_span = {
                "traceID": self._to_hex_id(span.trace_id),
                "spanID": self._to_hex_id(span.span_id),
                "operationName": span.name,
                "references": references,
                "startTime": start_time_us,
                "duration": duration_us,
                "tags": tags,
                "logs": logs,
                "processID": process_id_map.get(span.component, "p1"),
                "warnings": None
            }
            jaeger_spans.append(jaeger_span)
        
        # 构建最终的 Jaeger 格式
        result = {
            "data": [{
                "traceID": self._to_hex_id(trace.trace_id),
                "spans": jaeger_spans,
                "processes": processes,
                "warnings": None
            }],
            "total": 0,
            "limit": 0,
            "offset": 0,
            "errors": None
        }
        
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)
    
    def _to_hex_id(self, id_str: str) -> str:
        """将 ID 转换为 Jaeger 兼容的 16 进制格式 (32 字符 hex)"""
        return hashlib.md5(id_str.encode()).hexdigest()

