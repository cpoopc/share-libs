#!/usr/bin/env python3
"""
IVA Voice Call Log Analyzer - 数据模型定义

包含所有枚举类型和数据类定义。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

# ============================================================================
# 常量定义
# ============================================================================

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
TIMESTAMP_FORMAT_NO_MS = "%Y-%m-%dT%H:%M:%SZ"


# ============================================================================
# 枚举类型
# ============================================================================

class CallState(Enum):
    """通话状态机状态 (基于 voice-call-logs-analysis.md Section 3)"""
    INIT = "init"
    GREETING = "greeting"
    AFTER_GREETING = "after-greeting"
    LISTENING = "listening"
    ANSWERING = "answering"
    CANCELLING = "cancelling"
    AFTER_INTERRUPTION = "after-interruption"
    TERMINATING_CALL = "terminating-call"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class EventType(Enum):
    """事件类型"""
    # 连接阶段
    CALL_START = "call_start"
    GREETING_START = "greeting_start"
    RECONNECT = "reconnect"
    AGENT_INIT = "agent_init"
    # 语音识别
    INTERIM_TRANSCRIPT = "interim_transcript"
    FINAL_TRANSCRIPT = "final_transcript"
    # LLM 生成
    GENERATING_RESPONSE = "generating_response"
    LLM_REQUEST = "llm_request"
    TTFT_OBSERVED = "ttft_observed"
    LLM_GENERATE = "llm_generate"
    LLM_FINISHED = "llm_finished"
    # TTS
    TTS_SAYING = "tts_saying"
    TTS_SPOKEN = "tts_spoken"
    ALL_TTS_SPOKEN = "all_tts_spoken"
    TURN_COMPLETE = "turn_complete"
    # Filler
    FILLER_SCHEDULED = "filler_scheduled"
    FILLER_SPOKEN = "filler_spoken"
    # 打断
    INTERRUPTION = "interruption"
    INTERRUPTION_TRANSCRIPT = "interruption_transcript"
    TTS_CANCELLED = "tts_cancelled"
    # 结束
    CALL_CLOSE = "call_close"
    # 其他
    STATE_CHANGE = "state_change"
    LOG = "log"
    ERROR = "error"
    WARNING = "warning"


# ============================================================================
# 工具函数
# ============================================================================

def parse_timestamp(ts_str: str) -> Optional[datetime]:
    """
    解析时间戳字符串

    注意: 此函數委託給 shared.timestamp 模組。
    保留此函數以維持向後兼容性。
    """
    # 延遲導入以避免循環依賴和相對導入問題
    try:
        from ..shared.timestamp import parse_timestamp as _shared_parse_timestamp
        return _shared_parse_timestamp(ts_str)
    except ImportError:
        # Fallback: 直接實現（當無法使用相對導入時）
        if not ts_str:
            return None
        try:
            return datetime.strptime(ts_str, TIMESTAMP_FORMAT)
        except ValueError:
            try:
                return datetime.strptime(ts_str, TIMESTAMP_FORMAT_NO_MS)
            except ValueError:
                return None


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class LogEntry:
    """结构化日志条目 (Parser 输出)"""
    raw_line: str
    timestamp_str: str
    timestamp_dt: Optional[datetime]
    timestamp_ms: float  # 相对于会话开始的毫秒数
    level: str  # INFO, ERROR, WARN
    state: Optional[CallState]
    event_type: EventType
    message: str
    component: str  # 推断的组件: FSM, RemoteController, etc.

    # 提取的数据
    extracted_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CallMetrics:
    """通话性能指标 (Analyzer 输出)"""
    total_duration_ms: float = 0.0
    ttft_values: List[float] = field(default_factory=list)  # 首字延迟列表
    avg_ttft_ms: float = 0.0
    interruption_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    user_turns: int = 0  # 用户对话轮数
    agent_turns: int = 0  # Agent 回复轮数
    states_visited: Set[str] = field(default_factory=set)

    # LLM 相关
    llm_call_count: int = 0
    llm_total_latency_ms: float = 0.0
    llm_avg_latency_ms: float = 0.0

    # TTS 相关
    tts_phrase_count: int = 0
    tts_cancelled_count: int = 0


@dataclass
class TurnEvent:
    """Turn 内的事件"""
    timestamp: str
    timestamp_dt: datetime
    component: str
    event_type: EventType
    message: str
    duration_from_turn_start_ms: float = 0.0


@dataclass
class Turn:
    """对话轮次"""
    turn_number: int
    turn_type: str  # "greeting", "user_turn", "user_turn_continued"

    # 时间信息
    start_timestamp: Optional[str] = None
    end_timestamp: Optional[str] = None
    duration_ms: float = 0.0

    # 用户输入
    user_transcript: Optional[str] = None
    user_transcript_confidence: float = 0.0

    # AI 响应 (所有 phrases)
    ai_response: Optional[str] = None
    ai_phrases: List[str] = field(default_factory=list)

    # 状态流转
    states: List[str] = field(default_factory=list)

    # 是否被打断
    was_interrupted: bool = False

    # 事件列表
    events: List[TurnEvent] = field(default_factory=list)

    # LLM 调用
    llm_calls: List[Dict[str, Any]] = field(default_factory=list)

    # 工具调用
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)

    # 延迟分解
    latency_breakdown: Dict[str, float] = field(default_factory=dict)

    # TTFT
    ttft_ms: Optional[float] = None

    # 组件时间线 - 关键日志节点
    component_timeline: List[Dict[str, Any]] = field(default_factory=list)

    # 轮次中的异常列表
    # 每项结构: {"type": str, "severity": "info|warning|error", "message": str}
    anomalies: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "turn_number": self.turn_number,
            "turn_type": self.turn_type,
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "duration_ms": self.duration_ms,
            "user_transcript": self.user_transcript,
            "user_transcript_confidence": self.user_transcript_confidence,
            "ai_response": self.ai_response,
            "ai_phrases": self.ai_phrases,
            "states": self.states,
            "was_interrupted": self.was_interrupted,
            "ttft_ms": self.ttft_ms,
            "event_count": len(self.events),
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "latency_breakdown": self.latency_breakdown,
            "component_timeline": self.component_timeline,
            "anomalies": self.anomalies,
        }


@dataclass
class CallSession:
    """通话会话 (Sessionizer 输出)"""
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None

    # 日志条目
    logs: List[LogEntry] = field(default_factory=list)

    # Turn 列表
    turns: List[Turn] = field(default_factory=list)

    # 性能指标
    metrics: CallMetrics = field(default_factory=CallMetrics)

    # 错误和警告
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # 会话状态
    is_completed: bool = False
    termination_reason: str = "unknown"

    # 关键流程事件 (用于时序重建)
    critical_events: List[LogEntry] = field(default_factory=list)


@dataclass
class AnalysisReport:
    """分析报告 (Reporter 输入)"""
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None

    # Turn 列表
    turns: List[Turn] = field(default_factory=list)

    # 性能指标
    metrics: CallMetrics = field(default_factory=CallMetrics)

    # 错误和警告
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # 总体统计
    total_turns: int = 0
    total_duration_ms: float = 0.0
    avg_turn_duration_ms: float = 0.0

    # 终止信息
    is_completed: bool = False
    termination_reason: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "conversation_id": self.conversation_id,
            "total_turns": self.total_turns,
            "total_duration_ms": self.total_duration_ms,
            "avg_turn_duration_ms": self.avg_turn_duration_ms,
            "metrics": {
                "ttft_values": self.metrics.ttft_values,
                "avg_ttft_ms": self.metrics.avg_ttft_ms,
                "interruption_count": self.metrics.interruption_count,
                "error_count": self.metrics.error_count,
                "llm_call_count": self.metrics.llm_call_count,
                "llm_total_latency_ms": self.metrics.llm_total_latency_ms,
                "states_visited": list(self.metrics.states_visited),
            },
            "errors": self.errors,
            "warnings": self.warnings,
            "is_completed": self.is_completed,
            "termination_reason": self.termination_reason,
            "turns": [t.to_dict() for t in self.turns],
        }


# 保持向后兼容
TurnAnalysisReport = AnalysisReport

