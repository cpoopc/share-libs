#!/usr/bin/env python3
"""
IVA Log Loaders - IVA 日志加载器插件

每个加载器负责从特定组件加载日志，可声明依赖的 context 属性
"""

from ...loaders import LogLoader

# NCA, AIG, GMG 从 nova 模块导入
from ...nova import AIGLoader, GMGLoader, NCALoader
from .agent_service import AgentServiceLoader
from .assistant_runtime import AssistantRuntimeLoader
from .cprc import CPRCSGSLoader, CPRCSRSLoader

# 所有可用的加载器 (IVA session trace 需要的)
ALL_LOADERS = [
    AssistantRuntimeLoader,
    AgentServiceLoader,
    NCALoader,
    AIGLoader,  # AIG 依赖 NCA (request_id)
    GMGLoader,  # GMG 依赖 NCA (request_id -> log_context_RCRequestId)
    CPRCSRSLoader,
    CPRCSGSLoader,
]

# 默认启用的加载器（按 session_id 追踪时）
DEFAULT_SESSION_LOADERS = [
    "assistant_runtime",
    "agent_service",
    "nca",
    "aig",
    "gmg",
    "cprc_srs",
    "cprc_sgs",
]

# 默认启用的加载器（按 conversation_id 追踪时）
# 注意：cprc_srs/cprc_sgs 依赖 srs_session_id/sgs_session_id，
# 这些 ID 会从 assistant_runtime 日志中自动提取
DEFAULT_CONVERSATION_LOADERS = [
    "assistant_runtime",
    "agent_service",
    "nca",
    "aig",
    "gmg",
    "cprc_srs",
    "cprc_sgs",
]

__all__ = [
    "LogLoader",
    "AssistantRuntimeLoader",
    "AgentServiceLoader",
    "NCALoader",
    "AIGLoader",
    "GMGLoader",
    "CPRCSRSLoader",
    "CPRCSGSLoader",
    "ALL_LOADERS",
    "DEFAULT_SESSION_LOADERS",
    "DEFAULT_CONVERSATION_LOADERS",
]

