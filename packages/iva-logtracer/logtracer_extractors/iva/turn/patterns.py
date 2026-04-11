#!/usr/bin/env python3
"""
IVA Voice Call Log Analyzer - 日志模式定义

包含所有用于日志解析和事件识别的正则表达式模式。
"""

from typing import List, Tuple

from .models import EventType

# ============================================================================
# Turn 开始/结束模式
# ============================================================================

# Turn 开始模式 (按优先级排序)
TURN_START_PATTERNS: List[Tuple[str, str]] = [
    (r"\[state: init\] User connected, starting greeting", "greeting_start"),
    (r"\[state: listening\] Received transcript from user", "user_transcript_state"),
    (r"\[state: after-interruption\] Schedule fillers", "after_interruption"),
]

# Turn 结束模式
TURN_END_PATTERNS: List[Tuple[str, str]] = [
    (r"LLM generation and speaking has been completed", "llm_speaking_complete"),
]

# 打断检测模式
INTERRUPTION_PATTERNS: List[Tuple[str, str]] = [
    (r"Interrupting the generation", "interruption"),
    (r"Phrase has been cancelled", "phrase_cancelled"),
]

# 用于提取用户输入的模式
USER_INPUT_PATTERN = r"Generating response for:\s*(.+)$"

# 状态提取模式
STATE_PATTERN = r"\[state: ([a-z_-]+)\]"


# ============================================================================
# 关键事件模式 (用于 Parser 事件分类)
# ============================================================================

KEY_EVENT_PATTERNS: List[Tuple[str, EventType]] = [
    # 连接阶段
    (r"Open new call conversation", EventType.CALL_START),
    (r"User connected, starting greeting", EventType.GREETING_START),
    (r"User reconnected, starting listening", EventType.RECONNECT),
    (r"Sending init request", EventType.AGENT_INIT),
    (r"Received init:", EventType.AGENT_INIT),
    # 语音识别
    (r"Received interim transcript", EventType.INTERIM_TRANSCRIPT),
    (r"Received transcript from user", EventType.FINAL_TRANSCRIPT),
    # LLM 生成
    (r"Generating greeting", EventType.GENERATING_RESPONSE),
    (r"Generating response for:", EventType.GENERATING_RESPONSE),
    (r"Sending request", EventType.LLM_REQUEST),
    (r"Observed TTFT", EventType.TTFT_OBSERVED),
    (r"Received generate:", EventType.LLM_GENERATE),
    (r"Received end:", EventType.LLM_FINISHED),
    (r"LLM generation has finished", EventType.LLM_FINISHED),
    # TTS
    (r"Saying phrase:", EventType.TTS_SAYING),
    (r"Phrase has been spoken:", EventType.TTS_SPOKEN),
    (r"All phrases has been spoken", EventType.ALL_TTS_SPOKEN),
    (r"LLM generation and speaking has been completed", EventType.TURN_COMPLETE),
    # Filler
    (r"Schedule fillers", EventType.FILLER_SCHEDULED),
    (r"Filler phrase.*is spoken", EventType.FILLER_SPOKEN),
    # 打断
    (r"Interrupting the generation", EventType.INTERRUPTION),
    (r"Interrupting with final transcript", EventType.INTERRUPTION_TRANSCRIPT),
    (r"Phrase has been cancelled", EventType.TTS_CANCELLED),
    # 结束
    (r"Conversation close by event", EventType.CALL_CLOSE),
    # 错误和警告
    (r"error:|failed|failure|fatal", EventType.ERROR),
    (r"warn:|timeout", EventType.WARNING),
]

# 关键流程事件 (用于时序重建)
CRITICAL_EVENT_KEYWORDS: List[str] = [
    "Open new call", "starting greeting", "Saying phrase",
    "Received transcript from user", "Generating response",
    "Interrupting", "Close by event", "LLM generation and speaking"
]


# ============================================================================
# 组件时间线关键事件模式 (用于 _collect_component_timeline)
# ============================================================================

# Assistant Runtime 关键事件模式
# - 发送请求(grpc)
# - 第一次接收到回复/收到回复结束
# - 发起打断
# - tool call start/end
# - error
AR_TIMELINE_PATTERNS: List[Tuple[str, str, str]] = [
    # gRPC 请求 (严格匹配，排除普通 response)
    (r'Sending (init |generation )?request', 'grpc_send', 'AR'),
    (r'Generating response for:', 'grpc_send', 'AR'),
    # 第一次接收回复
    (r'Saying phrase:', 'first_response', 'AR'),
    # 收到回复结束
    (r'LLM generation has finished', 'response_end', 'AR'),
    (r'LLM generation and speaking has been completed', 'response_end', 'AR'),
    # 打断 (严格匹配，避免误匹配 "interruptible" / "uninterruptible")
    (r'Interrupt(ing|ed) the generation', 'interruption', 'AR'),
    (r'User interrupt', 'interruption', 'AR'),
    # Tool call start
    (r'"type"\s*:\s*"tool"', 'tool_call_start', 'AR'),
    (r'Calling (client |server )?tool', 'tool_call_start', 'AR'),
    (r'(clientTool|serverTool)\s*[:=]', 'tool_call_start', 'AR'),
    # Tool call end
    (r'Received toolResult', 'tool_call_end', 'AR'),
    (r'(Client |Server )?[Tt]ool completed', 'tool_call_end', 'AR'),
]

# NCA 关键事件模式
# - tool call start/end
# - llm request start/end
# - 生成回复(start/end)
# - error
NCA_TIMELINE_PATTERNS: List[Tuple[str, str, str]] = [
    # Tool call
    (r'(Calling|calling).*(tool|Tool)', 'tool_call_start', 'nca'),
    (r'(clientTool|serverTool)', 'tool_call_start', 'nca'),
    (r'(tool|Tool).*(completed|finished|result|response)', 'tool_call_end', 'nca'),
    # LLM request
    (r'(LLM|llm).*(request|call|start)', 'llm_request_start', 'nca'),
    (r'(request|send).*(LLM|llm|model)', 'llm_request_start', 'nca'),
    (r'(LLM|llm).*(response|complete|finish|end)', 'llm_request_end', 'nca'),
    # 生成回复
    (r'(Generat|generat).*(start|begin)', 'generation_start', 'nca'),
    (r'(Start|start).*(generat|response)', 'generation_start', 'nca'),
    (r'(Generat|generat).*(end|complete|finish)', 'generation_end', 'nca'),
    (r'(response|generation).*(complete|finish|end)', 'generation_end', 'nca'),
    # Error
    (r'(ERROR|Error|error)', 'error', 'nca'),
]

# AIG 关键事件模式
# - tool call start/end
# - 调用agent-service start/end
# - error
AIG_TIMELINE_PATTERNS: List[Tuple[str, str, str]] = [
    # Tool call
    (r'(Calling|calling).*(tool|Tool)', 'tool_call_start', 'aig'),
    (r'(tool|Tool).*(completed|finished|result|response)', 'tool_call_end', 'aig'),
    # Agent service call
    (r'(Calling|calling|request).*(agent|Agent)', 'agent_service_call_start', 'aig'),
    (r'(agent|Agent).*(response|complete|finish)', 'agent_service_call_end', 'aig'),
    # Error
    (r'(ERROR|Error|error)', 'error', 'aig'),
]

# GMG 关键事件模式
# - llm request start/end
# - 生成回复(start/end)
# - error
GMG_TIMELINE_PATTERNS: List[Tuple[str, str, str]] = [
    # LLM request
    (r'(Request|request).*(start|begin|received)', 'llm_request_start', 'gmg'),
    (r'(Sending|sending|forward).*(request|LLM|model)', 'llm_request_start', 'gmg'),
    (r'Request completed', 'llm_request_end', 'gmg'),
    (r'(Request|request).*(complete|finish|end)', 'llm_request_end', 'gmg'),
    (r'request_latency', 'llm_request_end', 'gmg'),
    # 生成回复
    (r'(Generat|generat).*(start|begin)', 'generation_start', 'gmg'),
    (r'(first|First).*(token|chunk)', 'generation_start', 'gmg'),
    (r'(Generat|generat).*(end|complete|finish)', 'generation_end', 'gmg'),
    (r'(Stream|stream).*(end|complete|finish)', 'generation_end', 'gmg'),
    # Error
    (r'(ERROR|Error|error)', 'error', 'gmg'),
]

# Agent Service 关键事件模式
# - tool call start/end
# - error
AGENT_SERVICE_TIMELINE_PATTERNS: List[Tuple[str, str, str]] = [
    # Tool call
    (r'(Calling|calling).*(tool|Tool)', 'tool_call_start', 'agent_service'),
    (r'(clientTool|serverTool)', 'tool_call_start', 'agent_service'),
    (r'(tool|Tool).*(completed|finished|result|response)', 'tool_call_end', 'agent_service'),
    # Error
    (r'(ERROR|Error|error)', 'error', 'agent_service'),
]

# 组件模式映射表
COMPONENT_TIMELINE_PATTERNS = {
    "nca": NCA_TIMELINE_PATTERNS,
    "aig": AIG_TIMELINE_PATTERNS,
    "gmg": GMG_TIMELINE_PATTERNS,
    "agent_service": AGENT_SERVICE_TIMELINE_PATTERNS,
}

