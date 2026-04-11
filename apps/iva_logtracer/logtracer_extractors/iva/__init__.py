#!/usr/bin/env python3
"""
IVA Session Tracer - IVA 会话追踪模块

插件化架构:
- TraceContext: 共享上下文
- LogLoader: 日志加载器插件接口
- SessionTraceOrchestrator: 编排器
"""

from .ai_extractor import AIAnalysisExtractor, save_ai_analysis_files
from .loaders import (
    ALL_LOADERS,
    DEFAULT_CONVERSATION_LOADERS,
    DEFAULT_SESSION_LOADERS,
    AgentServiceLoader,
    AssistantRuntimeLoader,
    CPRCSGSLoader,
    CPRCSRSLoader,
    LogLoader,
    NCALoader,
)
from .orchestrator import SessionTraceOrchestrator
from .trace_context import TraceContext

__all__ = [
    # 核心类
    "TraceContext",
    "SessionTraceOrchestrator",

    # AI Analysis
    "AIAnalysisExtractor",
    "save_ai_analysis_files",

    # Loaders
    "LogLoader",
    "AssistantRuntimeLoader",
    "AgentServiceLoader",
    "NCALoader",
    "CPRCSRSLoader",
    "CPRCSGSLoader",

    # 常量
    "ALL_LOADERS",
    "DEFAULT_SESSION_LOADERS",
    "DEFAULT_CONVERSATION_LOADERS",
]

