#!/usr/bin/env python3
"""
Span Model - 分布式追踪 Span 数据模型

参考 OpenTelemetry 设计，适配 IVA 日志追踪场景。

核心概念:
- Trace: 一次完整的对话会话 (conversation_id)
- Span: 一个操作的时间范围 (如 LLM 请求、工具调用)
- Parent/Child: Span 之间的层级关系
- Attributes: Span 的元数据
- Events: Span 内的时间点事件
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class SpanKind(Enum):
    """Span 类型 (参考 OpenTelemetry)"""
    INTERNAL = "INTERNAL"      # 内部操作
    SERVER = "SERVER"          # 服务端处理
    CLIENT = "CLIENT"          # 客户端调用
    PRODUCER = "PRODUCER"      # 生产消息
    CONSUMER = "CONSUMER"      # 消费消息


class SpanStatus(Enum):
    """Span 状态"""
    OK = "OK"                  # 成功
    ERROR = "ERROR"            # 错误
    UNSET = "UNSET"            # 未设置(进行中)
    CANCELLED = "CANCELLED"    # 已取消


@dataclass
class SpanEvent:
    """Span 内的事件点 (瞬时事件，没有持续时间)"""
    name: str                              # 事件名称
    timestamp: datetime                    # 事件时间
    attributes: Dict[str, Any] = field(default_factory=dict)  # 事件属性
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "timestamp": self.timestamp.isoformat(),
            "attributes": self.attributes,
        }


@dataclass
class Span:
    """
    Span - 表示一个操作的时间范围
    
    参考 OpenTelemetry Span 规范，包含:
    - 唯一标识: trace_id, span_id, parent_span_id
    - 时间信息: start_time, end_time, duration_ms
    - 操作信息: name, kind, component
    - 元数据: attributes, events
    - 状态: status, status_message
    """
    
    # === 核心标识 ===
    trace_id: str                          # Trace ID (conversation_id)
    span_id: str                           # Span ID (自动生成的 UUID)
    parent_span_id: Optional[str] = None   # 父 Span ID
    
    # === 时间信息 ===
    start_time: Optional[datetime] = None  # 开始时间
    end_time: Optional[datetime] = None    # 结束时间
    duration_ms: Optional[float] = None    # 持续时间(毫秒)
    
    # === 操作信息 ===
    name: str = ""                         # Span 名称 (如 "LLM Request", "Tool Call")
    kind: SpanKind = SpanKind.INTERNAL     # Span 类型
    component: str = ""                    # 组件名称 (如 "nca", "gmg")
    operation: str = ""                    # 操作类型 (如 "llm_request", "tool_call")
    
    # === 元数据 ===
    attributes: Dict[str, Any] = field(default_factory=dict)  # 属性
    events: List[SpanEvent] = field(default_factory=list)     # 事件列表
    
    # === 状态 ===
    status: SpanStatus = SpanStatus.UNSET  # Span 状态
    status_message: str = ""               # 状态消息
    
    # === 原始数据 ===
    start_log: Optional[Dict[str, Any]] = None  # 开始日志
    end_log: Optional[Dict[str, Any]] = None    # 结束日志
    
    def __post_init__(self):
        """初始化后处理"""
        if not self.span_id:
            self.span_id = str(uuid.uuid4())
        
        # 计算持续时间
        if self.start_time and self.end_time and not self.duration_ms:
            delta = self.end_time - self.start_time
            self.duration_ms = delta.total_seconds() * 1000
    
    def add_event(self, name: str, timestamp: datetime, attributes: Optional[Dict[str, Any]] = None):
        """添加事件"""
        event = SpanEvent(
            name=name,
            timestamp=timestamp,
            attributes=attributes or {}
        )
        self.events.append(event)
    
    def set_attribute(self, key: str, value: Any):
        """设置属性"""
        self.attributes[key] = value
    
    def set_status(self, status: SpanStatus, message: str = ""):
        """设置状态"""
        self.status = status
        self.status_message = message
    
    def finish(self, end_time: datetime):
        """结束 Span"""
        self.end_time = end_time
        if self.start_time:
            delta = end_time - self.start_time
            self.duration_ms = delta.total_seconds() * 1000
        
        # 如果状态未设置，标记为 OK
        if self.status == SpanStatus.UNSET:
            self.status = SpanStatus.OK
    
    def is_root(self) -> bool:
        """是否为根 Span"""
        return self.parent_span_id is None
    
    def is_complete(self) -> bool:
        """Span 是否完成"""
        return self.end_time is not None
    
    def get_offset_ms(self, base_time: datetime) -> float:
        """获取相对于基准时间的偏移(毫秒)"""
        if not self.start_time:
            return 0.0
        delta = self.start_time - base_time
        return delta.total_seconds() * 1000
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "kind": self.kind.value,
            "component": self.component,
            "operation": self.operation,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
            "events": [e.to_dict() for e in self.events],
            "status": self.status.value,
            "status_message": self.status_message,
        }


@dataclass
class Trace:
    """
    Trace - 表示一次完整的追踪
    
    包含多个 Span 的集合，提供树形结构的查询和导航
    """
    trace_id: str                          # Trace ID (conversation_id)
    session_id: Optional[str] = None       # Session ID
    spans: List[Span] = field(default_factory=list)  # Span 列表
    
    # 元数据
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def add_span(self, span: Span):
        """添加 Span"""
        self.spans.append(span)
        
        # 更新 Trace 时间范围
        if span.start_time:
            if not self.start_time or span.start_time < self.start_time:
                self.start_time = span.start_time
        
        if span.end_time:
            if not self.end_time or span.end_time > self.end_time:
                self.end_time = span.end_time
        
        # 重新计算持续时间
        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
            self.duration_ms = delta.total_seconds() * 1000
    
    def get_root_spans(self) -> List[Span]:
        """获取根 Span (没有父 Span 的)"""
        return [s for s in self.spans if s.is_root()]
    
    def get_children(self, parent_span_id: str) -> List[Span]:
        """获取子 Span"""
        return [s for s in self.spans if s.parent_span_id == parent_span_id]
    
    def get_span_by_id(self, span_id: str) -> Optional[Span]:
        """根据 ID 获取 Span"""
        for span in self.spans:
            if span.span_id == span_id:
                return span
        return None
    
    def get_span_tree(self) -> List[Dict[str, Any]]:
        """
        获取 Span 树形结构
        
        Returns:
            树形结构的 Span 列表
        """
        def build_tree(parent_id: Optional[str], level: int = 0) -> List[Dict[str, Any]]:
            result = []
            children = [s for s in self.spans if s.parent_span_id == parent_id]
            children.sort(key=lambda s: s.start_time or datetime.min)
            
            for span in children:
                node = {
                    "span": span,
                    "level": level,
                    "children": build_tree(span.span_id, level + 1)
                }
                result.append(node)
            return result
        
        return build_tree(None)
    
    def get_critical_path(self) -> List[Span]:
        """
        获取关键路径 (耗时最长的调用链)
        
        Returns:
            关键路径上的 Span 列表
        """
        if not self.spans:
            return []
        
        # 找到耗时最长的根 Span
        root_spans = self.get_root_spans()
        if not root_spans:
            return []
        
        longest_root = max(root_spans, key=lambda s: s.duration_ms or 0)
        
        # 递归找到每一层耗时最长的子 Span
        def find_longest_child(parent_span: Span) -> List[Span]:
            children = self.get_children(parent_span.span_id)
            if not children:
                return [parent_span]
            
            longest_child = max(children, key=lambda s: s.duration_ms or 0)
            return [parent_span] + find_longest_child(longest_child)
        
        return find_longest_child(longest_root)
    
    def get_component_summary(self) -> Dict[str, Dict[str, Any]]:
        """获取各组件的统计摘要"""
        summary: Dict[str, Dict[str, Any]] = {}
        
        for span in self.spans:
            comp = span.component or "unknown"
            if comp not in summary:
                summary[comp] = {
                    "span_count": 0,
                    "total_duration_ms": 0,
                    "avg_duration_ms": 0,
                    "error_count": 0,
                    "operations": set(),
                }
            
            summary[comp]["span_count"] += 1
            if span.duration_ms:
                summary[comp]["total_duration_ms"] += span.duration_ms
            if span.status == SpanStatus.ERROR:
                summary[comp]["error_count"] += 1
            summary[comp]["operations"].add(span.operation)
        
        # 计算平均值，转换 set 为 list
        for comp, stats in summary.items():
            if stats["span_count"] > 0:
                stats["avg_duration_ms"] = stats["total_duration_ms"] / stats["span_count"]
            stats["operations"] = list(stats["operations"])
        
        return summary
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
            "spans": [s.to_dict() for s in self.spans],
            "component_summary": self.get_component_summary(),
        }
