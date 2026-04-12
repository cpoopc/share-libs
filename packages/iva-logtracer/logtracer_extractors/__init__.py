"""
IVA Log Tracer extractors package

模块:
- loaders: 日志加载器公共接口
- iva: IVA 会话追踪
- nova: Nova 组件 (NCA, AIG, GMG)
- platform: Platform 组件 (AGW)

注意: 通用的 Kibana 功能在已安装的 `cptools-kibana` 包中
"""

# 从 cptools-kibana 导入通用能力 (backward compatibility)
from cptools_kibana import (
    KibanaClient,
    KibanaConfig,
    LogSearcher,
    QueryBuilder,
    parse_time_range,
)

# IVA 模块
from .iva import (
    ALL_LOADERS,
    DEFAULT_CONVERSATION_LOADERS,
    DEFAULT_SESSION_LOADERS,
    AgentServiceLoader,
    AssistantRuntimeLoader,
    CPRCSGSLoader,
    CPRCSRSLoader,
    SessionTraceOrchestrator,
    TraceContext,
)

# 公共 Loader 接口
from .loaders import LogLoader, TraceContextProtocol

# Nova 模块
from .nova import AIGLoader, GMGLoader, NCALoader

# Platform 模块
from .platform import AGWLoader

__all__ = [
    # Kibana Client
    "KibanaClient",
    "KibanaConfig",
    "QueryBuilder",
    "parse_time_range",
    "LogSearcher",

    # 公共接口
    "LogLoader",
    "TraceContextProtocol",

    # Nova 模块
    "NCALoader",
    "AIGLoader",
    "GMGLoader",

    # Platform 模块
    "AGWLoader",

    # IVA 模块
    "TraceContext",
    "SessionTraceOrchestrator",
    "AssistantRuntimeLoader",
    "AgentServiceLoader",
    "CPRCSRSLoader",
    "CPRCSGSLoader",
    "ALL_LOADERS",
    "DEFAULT_SESSION_LOADERS",
    "DEFAULT_CONVERSATION_LOADERS",
]
