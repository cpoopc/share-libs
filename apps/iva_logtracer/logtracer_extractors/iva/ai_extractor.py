#!/usr/bin/env python3
"""
AI Analysis Extractor - 提取关键日志节点生成 AI 分析友好的输出

从各组件日志中提取关键事件，生成：
1. session_trace.json - 简化的 trace JSON，包含所有组件的关键事件
2. key_events.log - 简洁的文本日志，便于 AI 阅读
3. component_summary.json - 各组件关键指标汇总

组件关键事件定义 (参考 info.md):
- assistant_runtime: 发送请求(grpc), 第一次接收到回复/收到回复结束, 发起打断, tool call start/end, error
- nca: tool call start/end, llm request start/end, 生成回复(start/end), error
- aig: tool call start/end, 调用agent-service start/end, error
- gmg: llm request start/end, 生成回复(start/end), error
- agent_service: tool call start/end, error

重構說明：
- 使用 shared.timestamp 統一時間戳處理
- 使用 shared.log_normalizer 統一日誌字段
- 使用 turn.event_registry 作為事件定義的 Single Source of Truth
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 使用共享模組 - 支持相對和絕對導入
try:
    from .shared.log_normalizer import normalize_log_entry
    from .shared.timestamp import parse_timestamp
    from .turn.event_registry import (
        enrich_event,
        get_patterns_for_component,
    )
except ImportError:
    from shared.log_normalizer import normalize_log_entry
    from shared.timestamp import parse_timestamp
    from turn.event_registry import (
        enrich_event,
        get_patterns_for_component,
    )


class AIAnalysisExtractor:
    """AI 分析数据提取器 - 使用 event_registry 作為 Single Source of Truth"""

    # 支持的組件列表
    SUPPORTED_COMPONENTS = [
        'assistant_runtime', 'nca', 'aig', 'gmg',
        'agent_service', 'cprc_srs', 'cprc_sgs'
    ]

    def __init__(self, logs: Dict[str, List[Dict[str, Any]]]):
        """
        初始化提取器

        Args:
            logs: 按组件分组的日志字典
        """
        self.logs = logs
        self.key_events: List[Dict[str, Any]] = []
        self.component_metrics: Dict[str, Dict[str, Any]] = {}

    def extract(self) -> Dict[str, Any]:
        """执行提取，返回 AI 分析友好的结构"""
        self.key_events = []
        self.component_metrics = {}

        # 从各组件提取关键事件 - 使用 event_registry
        for component in self.SUPPORTED_COMPONENTS:
            component_logs = self.logs.get(component, [])
            if not component_logs:
                continue

            # 從 event_registry 獲取組件模式
            patterns = get_patterns_for_component(component)
            events = self._extract_component_events(component, component_logs, patterns)
            self.key_events.extend(events)

            # 收集组件指标
            self.component_metrics[component] = self._collect_component_metrics(
                component, component_logs, events
            )

        # 按时间排序
        self.key_events.sort(key=lambda x: x.get("timestamp", ""))

        return {
            "key_events": self.key_events,
            "component_metrics": self.component_metrics,
            "timeline": self._build_timeline(),
        }

    def _extract_component_events(
        self,
        component: str,
        logs: List[Dict[str, Any]],
        patterns: List[tuple]
    ) -> List[Dict[str, Any]]:
        """从组件日志中提取关键事件 - 使用標準化日誌和 event_registry"""
        events = []

        for raw_log in logs:
            # 標準化日誌字段
            log = normalize_log_entry(raw_log, component)
            message = log['message']
            level = log['level']
            timestamp = log['timestamp']

            # 检查是否为错误日志
            if level in ("ERROR", "FATAL"):
                events.append({
                    "timestamp": timestamp,
                    "component": component,
                    "event_type": "error",
                    "level": level,
                    "message": message[:200],
                    "logger": log['logger'],
                })
                continue

            # 检查是否为警告
            if level in ("WARN", "WARNING"):
                if any(kw in message.lower() for kw in ["timeout", "deadline", "retry"]):
                    events.append({
                        "timestamp": timestamp,
                        "component": component,
                        "event_type": "warning",
                        "level": level,
                        "message": message[:200],
                    })
                    continue

            # 匹配关键事件模式 - 使用 event_registry 模式
            for pattern, event_type in patterns:
                if re.search(pattern, message, re.IGNORECASE):
                    event = {
                        "timestamp": timestamp,
                        "component": component,
                        "event_type": event_type,
                        "message": message[:200],
                    }

                    # 使用統一的 enrich_event 函數
                    enrich_event(event, raw_log)
                    events.append(event)
                    break  # 每条日志只匹配一个事件

        return events

    def _collect_component_metrics(
        self,
        component: str,
        logs: List[Dict[str, Any]],
        events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """收集组件级别的指标"""
        metrics: Dict[str, Any] = {
            "total_logs": len(logs),
            "key_events_count": len(events),
            "error_count": sum(1 for e in events if e.get("event_type") == "error"),
            "warning_count": sum(1 for e in events if e.get("event_type") == "warning"),
        }

        # GMG 特有指标
        if component == "gmg":
            latencies = [log.get("request_latency", 0) for log in logs if log.get("request_latency")]
            if latencies:
                metrics["llm_call_count"] = len(latencies)
                metrics["avg_latency_ms"] = sum(latencies) / len(latencies)
                metrics["max_latency_ms"] = max(latencies)
                metrics["total_latency_ms"] = sum(latencies)

            tokens = [log.get("total_tokens", 0) for log in logs if log.get("total_tokens")]
            if tokens:
                metrics["total_tokens"] = sum(tokens)

        # 事件类型统计
        event_types: Dict[str, int] = {}
        for e in events:
            et = e.get("event_type", "unknown")
            event_types[et] = event_types.get(et, 0) + 1
        metrics["event_types"] = event_types

        return metrics

    def _build_timeline(self) -> List[Dict[str, Any]]:
        """构建简化的时间线，用于 AI 分析"""
        timeline = []
        start_ts: Optional[datetime] = None

        for event in self.key_events:
            ts = parse_timestamp(event.get("timestamp", ""))
            if ts:
                if start_ts is None:
                    start_ts = ts
                offset_ms = (ts - start_ts).total_seconds() * 1000
            else:
                offset_ms = 0

            # 简化的时间线条目
            entry = {
                "offset_ms": round(offset_ms, 1),
                "component": event.get("component", ""),
                "event": event.get("event_type", ""),
            }

            # 添加关键信息
            if event.get("state"):
                entry["state"] = event["state"]
            if event.get("transcript"):
                entry["transcript"] = event["transcript"]
            if event.get("phrase"):
                entry["phrase"] = event["phrase"]
            if event.get("tool_name"):
                entry["tool_name"] = event["tool_name"]
            if event.get("request_latency_ms"):
                entry["latency_ms"] = event["request_latency_ms"]
            if event.get("level") in ("ERROR", "FATAL"):
                entry["message"] = event.get("message", "")[:100]

            timeline.append(entry)

        return timeline


def save_ai_analysis_files(
    output_dir: Path,
    logs: Dict[str, List[Dict[str, Any]]],
    summary: Dict[str, Any]
) -> Dict[str, Path]:
    """
    保存 AI 分析文件到输出目录

    Args:
        output_dir: 输出目录
        logs: 按组件分组的日志
        summary: 会话摘要信息

    Returns:
        保存的文件路径字典
    """
    ai_dir = output_dir / "ai_analysis"
    ai_dir.mkdir(parents=True, exist_ok=True)

    # 提取关键事件
    extractor = AIAnalysisExtractor(logs)
    result = extractor.extract()

    saved_files: Dict[str, Path] = {}

    # 1. 保存 session_trace.json
    trace_data = {
        "session_id": summary.get("session_id"),
        "conversation_id": summary.get("conversation_id"),
        "srs_session_id": summary.get("srs_session_id"),
        "sgs_session_id": summary.get("sgs_session_id"),
        "component_metrics": result["component_metrics"],
        "key_events": result["key_events"],
        "timeline": result["timeline"],
    }
    trace_path = ai_dir / "session_trace.json"
    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(trace_data, f, indent=2, ensure_ascii=False, default=str)
    saved_files["session_trace.json"] = trace_path

    # 2. 保存 key_events.log (文本格式，便于 AI 阅读)
    log_lines = []
    log_lines.append(f"# IVA Session Trace - AI Analysis")
    log_lines.append(f"# Session ID: {summary.get('session_id')}")
    log_lines.append(f"# Conversation ID: {summary.get('conversation_id')}")
    log_lines.append("")
    log_lines.append("## Key Events Timeline")
    log_lines.append("")

    for event in result["key_events"]:
        ts = event.get("timestamp", "")[:23]  # 截断到毫秒
        comp = event.get("component", "")[:10].ljust(10)
        etype = event.get("event_type", "")[:20].ljust(20)
        msg = event.get("message", "")[:100]

        # 添加额外上下文
        extra = ""
        if event.get("state"):
            extra = f" [state={event['state']}]"
        elif event.get("transcript"):
            extra = f' [user: "{event["transcript"]}"]'
        elif event.get("phrase"):
            extra = f' [ai: "{event["phrase"]}"]'
        elif event.get("tool_name"):
            extra = f" [tool={event['tool_name']}]"
        elif event.get("request_latency_ms"):
            extra = f" [latency={event['request_latency_ms']}ms]"

        log_lines.append(f"[{ts}] [{comp}] {etype}{extra}")
        if event.get("event_type") in ("error", "warning"):
            log_lines.append(f"    └─ {msg}")

    log_path = ai_dir / "key_events.log"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))
    saved_files["key_events.log"] = log_path

    # 3. 保存 component_summary.json
    summary_data = {
        "session_id": summary.get("session_id"),
        "conversation_id": summary.get("conversation_id"),
        "component_metrics": result["component_metrics"],
        "total_key_events": len(result["key_events"]),
        "total_errors": sum(
            m.get("error_count", 0) for m in result["component_metrics"].values()
        ),
        "total_warnings": sum(
            m.get("warning_count", 0) for m in result["component_metrics"].values()
        ),
    }
    summary_path = ai_dir / "component_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2, ensure_ascii=False)
    saved_files["component_summary.json"] = summary_path

    return saved_files

