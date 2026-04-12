#!/usr/bin/env python3
"""
Span Correlator - Span 关联器

建立 Span 之间的父子关系和因果关系:
1. 时间包含关系: 如果 Span A 完全包含 Span B，则 A 是 B 的父
2. 组件调用链: assistant_runtime -> nca -> gmg
3. 操作依赖: llm_request 包含 generation
4. 工具调用链: tool_call -> agent_service_call

关联策略:
- Level 1: 显式调用关系 (gRPC request/response)
- Level 2: 时间包含关系 (嵌套)
- Level 3: 组件间的逻辑依赖
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

try:
    from ..correlation_graph import is_downstream_component
    from .span_model import Span, Trace
except ImportError:
    try:
        from extractors.iva.correlation_graph import is_downstream_component
    except ImportError:
        from correlation_graph import is_downstream_component
    from span_model import Span, Trace

# 操作包含关系 (父操作 -> 子操作列表)
OPERATION_CONTAINS = {
    "llm_request": ["generation", "first_token"],
    "generation": ["first_token"],
    "tool_call": ["agent_service_call"],
    "answering": ["llm_request", "generation", "tts_synthesis"],
    "greeting": ["llm_request", "generation", "tts_synthesis"],
}


class SpanCorrelator:
    """
    Span 关联器
    
    负责建立 Span 之间的父子关系
    """
    
    def __init__(self, time_tolerance_ms: float = 100):
        """
        初始化关联器
        
        Args:
            time_tolerance_ms: 时间容差(毫秒)，用于判断时间包含关系
        """
        self.time_tolerance_ms = time_tolerance_ms
        self.time_tolerance = timedelta(milliseconds=time_tolerance_ms)
    
    def correlate(self, spans: List[Span]) -> Trace:
        """
        关联 Span，建立父子关系
        
        Args:
            spans: Span 列表
        
        Returns:
            包含关联关系的 Trace
        """
        if not spans:
            trace_id = "unknown"
        else:
            trace_id = spans[0].trace_id
        
        trace = Trace(trace_id=trace_id)
        
        # 按时间排序
        sorted_spans = sorted(spans, key=lambda s: s.start_time or datetime.min)
        
        # 为每个 Span 查找父 Span
        for i, span in enumerate(sorted_spans):
            parent = self._find_parent(span, sorted_spans[:i])
            if parent:
                span.parent_span_id = parent.span_id
            
            trace.add_span(span)
        
        return trace
    
    def _find_parent(self, span: Span, candidates: List[Span]) -> Optional[Span]:
        """
        为 Span 查找最合适的父 Span
        
        Args:
            span: 目标 Span
            candidates: 候选父 Span 列表 (已按时间排序)
        
        Returns:
            父 Span，如果没找到则返回 None
        """
        if not candidates:
            return None
        
        # 候选列表：满足时间包含条件的 Span
        valid_candidates: List[Tuple[Span, int]] = []
        
        for candidate in candidates:
            score = self._calculate_parent_score(span, candidate)
            if score > 0:
                valid_candidates.append((candidate, score))
        
        if not valid_candidates:
            return None
        
        # 选择得分最高的作为父 Span
        valid_candidates.sort(key=lambda x: x[1], reverse=True)
        return valid_candidates[0][0]
    
    def _calculate_parent_score(self, child: Span, parent: Span) -> int:
        """
        计算父子关系的得分
        
        得分越高，越可能是父子关系
        
        Args:
            child: 子 Span
            parent: 候选父 Span
        
        Returns:
            得分 (0 表示不可能是父子关系)
        """
        score = 0
        
        # 检查时间包含关系
        if not self._is_time_contained(child, parent):
            return 0  # 时间不包含，不可能是父子关系
        
        score += 100  # 基础分：时间包含
        
        # 检查组件调用链
        if self._is_component_call_chain(child.component, parent.component):
            score += 50
        
        # 检查操作包含关系
        if self._is_operation_contained(child.operation, parent.operation):
            score += 30
        
        # 同组件的 Span，优先级降低 (可能是并行操作)
        if child.component == parent.component:
            score -= 20
        
        # 时间越接近，得分越高
        time_gap = self._calculate_time_gap(child, parent)
        if time_gap < 100:  # 100ms 内
            score += 20
        elif time_gap < 1000:  # 1s 内
            score += 10
        
        # 父 Span 越小(duration)，越可能是直接父级
        if parent.duration_ms:
            if parent.duration_ms < 1000:  # 1s 内
                score += 10
            elif parent.duration_ms < 5000:  # 5s 内
                score += 5
        
        return score
    
    def _is_time_contained(self, child: Span, parent: Span) -> bool:
        """
        检查子 Span 的时间是否被父 Span 包含
        
        允许一定的时间容差
        """
        if not child.start_time or not parent.start_time:
            return False
        
        # 父 Span 必须有结束时间，或者子 Span 开始时间在父 Span 开始时间之后
        if not parent.end_time:
            # 父 Span 未结束，只检查开始时间
            return child.start_time >= (parent.start_time - self.time_tolerance)
        
        if not child.end_time:
            # 子 Span 未结束，只检查开始时间在父 Span 范围内
            return (child.start_time >= (parent.start_time - self.time_tolerance) and
                    child.start_time <= (parent.end_time + self.time_tolerance))
        
        # 完整检查: child.start >= parent.start and child.end <= parent.end (允许容差)
        return (child.start_time >= (parent.start_time - self.time_tolerance) and
                child.end_time <= (parent.end_time + self.time_tolerance))
    
    def _is_component_call_chain(self, child_component: str, parent_component: str) -> bool:
        """检查是否是组件调用链"""
        return is_downstream_component(parent_component, child_component)
    
    def _is_operation_contained(self, child_operation: str, parent_operation: str) -> bool:
        """检查操作包含关系"""
        children = OPERATION_CONTAINS.get(parent_operation, [])
        return child_operation in children
    
    def _calculate_time_gap(self, child: Span, parent: Span) -> float:
        """
        计算子 Span 和父 Span 的时间间隔(毫秒)
        
        返回子 Span 开始时间和父 Span 开始时间的差值
        """
        if not child.start_time or not parent.start_time:
            return float('inf')
        
        gap = child.start_time - parent.start_time
        return abs(gap.total_seconds() * 1000)


def correlate_spans(spans: List[Span]) -> Trace:
    """
    便捷函数：关联 Span
    
    Args:
        spans: Span 列表
    
    Returns:
        关联后的 Trace
    """
    correlator = SpanCorrelator()
    return correlator.correlate(spans)
