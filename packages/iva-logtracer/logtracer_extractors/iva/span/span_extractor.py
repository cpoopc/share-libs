#!/usr/bin/env python3
"""
Span Extractor - 从日志中提取 Span

从标准化的日志中识别并构建 Span:
1. 匹配 start/end 事件对，构建 Span
2. 识别单点事件，作为 SpanEvent 附加到父 Span
3. 提取 Span 的属性和元数据

依赖:
- event_registry: 事件定义和匹配规则
- span_model: Span 数据模型
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    from ..shared.log_normalizer import normalize_log_entry
    from ..shared.timestamp import parse_timestamp
    from ..turn.event_registry import (
        EVENT_REGISTRY,
        extract_event_details,
        get_patterns_for_component,
        match_event_type,
    )
    from .span_model import Span, SpanEvent, SpanKind, SpanStatus
except ImportError:
    import sys
    from pathlib import Path
    _current_dir = Path(__file__).parent
    sys.path.insert(0, str(_current_dir.parent))
    
    from shared.log_normalizer import normalize_log_entry
    from shared.timestamp import parse_timestamp
    from span.span_model import Span, SpanEvent, SpanKind, SpanStatus
    from turn.event_registry import (
        EVENT_REGISTRY,
        extract_event_details,
        get_patterns_for_component,
        match_event_type,
    )


# 组件到 SpanKind 的映射
COMPONENT_TO_SPAN_KIND: Dict[str, SpanKind] = {
    "assistant_runtime": SpanKind.SERVER,
    "nca": SpanKind.INTERNAL,
    "aig": SpanKind.CLIENT,
    "gmg": SpanKind.CLIENT,
    "agent_service": SpanKind.SERVER,
    "cprc_srs": SpanKind.SERVER,
    "cprc_sgs": SpanKind.SERVER,
}


class SpanExtractor:
    """
    Span 提取器
    
    从日志中提取 Span 的主要逻辑:
    1. 按组件分组处理日志
    2. 匹配 start/end 事件对
    3. 构建 Span 对象
    4. 处理单点事件
    """
    
    def __init__(self, trace_id: str, session_id: Optional[str] = None):
        """
        初始化提取器
        
        Args:
            trace_id: Trace ID (通常是 conversation_id)
            session_id: Session ID (可选)
        """
        self.trace_id = trace_id
        self.session_id = session_id
        
        # 提取状态
        self.spans: List[Span] = []
        self.pending_starts: Dict[str, List[Tuple[str, datetime, Dict[str, Any]]]] = {}
        self.orphan_events: List[SpanEvent] = []
    
    def extract_from_logs(self, logs: Dict[str, List[Dict[str, Any]]]) -> List[Span]:
        """
        从按组件分组的日志中提取 Span
        
        Args:
            logs: 按组件分组的日志字典 {component: [log1, log2, ...]}
        
        Returns:
            提取的 Span 列表
        """
        self.spans = []
        self.pending_starts = {}
        self.orphan_events = []
        
        # 按组件处理
        for component, component_logs in logs.items():
            self._process_component_logs(component, component_logs)
        
        # 处理未配对的 start 事件 (创建未完成的 Span)
        self._finalize_pending_spans()
        
        # 按时间排序
        self.spans.sort(key=lambda s: s.start_time or datetime.min)
        
        return self.spans
    
    def _process_component_logs(self, component: str, logs: List[Dict[str, Any]]):
        """处理单个组件的日志"""
        patterns = get_patterns_for_component(component)
        if not patterns:
            return

        # 按时间戳排序日志 (确保 start 事件在 end 事件之前)
        def get_timestamp(log):
            ts = log.get('@timestamp') or log.get('timestamp') or ''
            return ts

        sorted_logs = sorted(logs, key=get_timestamp)

        for raw_log in sorted_logs:
            # 标准化日志
            log = normalize_log_entry(raw_log, component)
            message = log['message']
            timestamp = log['timestamp']
            
            # 匹配事件类型
            event_type = match_event_type(message, component)
            if not event_type:
                continue
            
            # 解析时间戳
            dt = parse_timestamp(timestamp)
            if not dt:
                continue
            
            # 提取事件详情
            details = extract_event_details(event_type, message, raw_log)
            
            # 判断是 start/end 还是 standalone
            if event_type.endswith('_start'):
                self._handle_start_event(event_type, dt, log, raw_log, details)
            elif event_type.endswith('_end'):
                self._handle_end_event(event_type, dt, log, raw_log, details)
            else:
                self._handle_standalone_event(event_type, dt, log, details)
    
    def _handle_start_event(
        self,
        event_type: str,
        timestamp: datetime,
        log: Dict[str, Any],
        raw_log: Dict[str, Any],
        details: Dict[str, Any]
    ):
        """处理 start 事件"""
        # 提取 base_type 和 pairing_key
        base_type = event_type.replace('_start', '')
        pairing_key = details.get('pairing_key', base_type)
        
        # 存储到 pending_starts
        key = f"{log['component']}:{pairing_key}"
        if key not in self.pending_starts:
            self.pending_starts[key] = []
        
        self.pending_starts[key].append((event_type, timestamp, {
            'log': log,
            'raw_log': raw_log,
            'details': details,
        }))
    
    def _handle_end_event(
        self,
        event_type: str,
        timestamp: datetime,
        log: Dict[str, Any],
        raw_log: Dict[str, Any],
        details: Dict[str, Any]
    ):
        """处理 end 事件"""
        base_type = event_type.replace('_end', '')
        pairing_key = details.get('pairing_key', base_type)
        
        # 查找对应的 start 事件
        key = f"{log['component']}:{pairing_key}"
        if key not in self.pending_starts or not self.pending_starts[key]:
            # 没有找到 start，创建一个不完整的 Span
            span = self._create_span_from_end(base_type, log, raw_log, details, timestamp)
            self.spans.append(span)
            return
        
        # 取出最近的 start
        start_event_type, start_time, start_data = self.pending_starts[key].pop(0)
        if not self.pending_starts[key]:
            del self.pending_starts[key]
        
        # 创建 Span
        span = self._create_span(
            base_type=base_type,
            component=log['component'],
            start_time=start_time,
            end_time=timestamp,
            start_log=start_data['raw_log'],
            end_log=raw_log,
            start_details=start_data['details'],
            end_details=details,
        )
        self.spans.append(span)
    
    def _handle_standalone_event(
        self,
        event_type: str,
        timestamp: datetime,
        log: Dict[str, Any],
        details: Dict[str, Any]
    ):
        """
        处理单点事件
        
        单点事件可以:
        1. 作为独立的 Span (duration = 0)
        2. 作为 SpanEvent 附加到当前活跃的 Span (未实现)
        """
        # 创建一个零持续时间的 Span
        span = Span(
            trace_id=self.trace_id,
            span_id=f"{event_type}_{timestamp.timestamp()}",
            name=self._get_display_name(event_type),
            kind=COMPONENT_TO_SPAN_KIND.get(log['component'], SpanKind.INTERNAL),
            component=log['component'],
            operation=event_type,
            start_time=timestamp,
            end_time=timestamp,
            duration_ms=0,
            attributes=details,
            start_log=log,
        )
        
        # 根据事件类型设置状态
        if event_type == 'error' or log['level'] == 'ERROR':
            span.set_status(SpanStatus.ERROR, log['message'][:200])
        elif event_type == 'interruption':
            span.set_status(SpanStatus.CANCELLED, "User interrupted")
        else:
            span.set_status(SpanStatus.OK)
        
        self.spans.append(span)
    
    def _create_span(
        self,
        base_type: str,
        component: str,
        start_time: datetime,
        end_time: datetime,
        start_log: Dict[str, Any],
        end_log: Dict[str, Any],
        start_details: Dict[str, Any],
        end_details: Dict[str, Any],
    ) -> Span:
        """创建完整的 Span"""
        # 合并属性
        attributes = {**start_details, **end_details}
        
        span = Span(
            trace_id=self.trace_id,
            span_id=f"{base_type}_{component}_{start_time.timestamp()}",
            name=self._get_display_name(base_type),
            kind=COMPONENT_TO_SPAN_KIND.get(component, SpanKind.INTERNAL),
            component=component,
            operation=base_type,
            start_time=start_time,
            end_time=end_time,
            attributes=attributes,
            start_log=start_log,
            end_log=end_log,
        )
        
        # 设置状态
        if end_log.get('level') == 'ERROR':
            span.set_status(SpanStatus.ERROR, end_log.get('message', '')[:200])
        else:
            span.set_status(SpanStatus.OK)
        
        return span
    
    def _create_span_from_end(
        self,
        base_type: str,
        log: Dict[str, Any],
        raw_log: Dict[str, Any],
        details: Dict[str, Any],
        end_time: datetime
    ) -> Span:
        """从 end 事件创建不完整的 Span (没有 start)"""
        span = Span(
            trace_id=self.trace_id,
            span_id=f"{base_type}_{log['component']}_incomplete_{end_time.timestamp()}",
            name=f"{self._get_display_name(base_type)} (incomplete)",
            kind=COMPONENT_TO_SPAN_KIND.get(log['component'], SpanKind.INTERNAL),
            component=log['component'],
            operation=base_type,
            start_time=end_time,  # 使用 end_time 作为 start_time
            end_time=end_time,
            duration_ms=0,
            attributes=details,
            end_log=raw_log,
        )
        
        span.set_status(SpanStatus.OK)
        return span
    
    def _finalize_pending_spans(self):
        """处理未配对的 start 事件"""
        for key, starts in self.pending_starts.items():
            for event_type, start_time, start_data in starts:
                base_type = event_type.replace('_start', '')
                log = start_data['log']
                
                # 创建未完成的 Span
                span = Span(
                    trace_id=self.trace_id,
                    span_id=f"{base_type}_{log['component']}_unfinished_{start_time.timestamp()}",
                    name=f"{self._get_display_name(base_type)} (unfinished)",
                    kind=COMPONENT_TO_SPAN_KIND.get(log['component'], SpanKind.INTERNAL),
                    component=log['component'],
                    operation=base_type,
                    start_time=start_time,
                    attributes=start_data['details'],
                    start_log=start_data['raw_log'],
                )
                
                # 状态设置为 UNSET (进行中)
                span.set_status(SpanStatus.UNSET, "No matching end event found")
                self.spans.append(span)
    
    def _get_display_name(self, event_type: str) -> str:
        """获取事件的显示名称"""
        base_type = event_type.replace('_start', '').replace('_end', '')
        config = EVENT_REGISTRY.get(base_type, {})
        return config.get('display_name', event_type)


def extract_spans_from_logs(
    logs: Dict[str, List[Dict[str, Any]]],
    conversation_id: str,
    session_id: Optional[str] = None
) -> List[Span]:
    """
    便捷函数：从日志中提取 Span
    
    Args:
        logs: 按组件分组的日志
        conversation_id: Conversation ID (作为 trace_id)
        session_id: Session ID (可选)
    
    Returns:
        Span 列表
    """
    extractor = SpanExtractor(trace_id=conversation_id, session_id=session_id)
    return extractor.extract_from_logs(logs)
