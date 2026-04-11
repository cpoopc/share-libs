#!/usr/bin/env python3
"""
IVA AgentServiceLoader - Agent Service 日志加载器

特点:
- 依赖 conversation_id
- 使用 conversationId 字段查询
"""

from typing import TYPE_CHECKING

try:
    from ...loaders import LogLoader
except ImportError:
    from loaders import LogLoader

if TYPE_CHECKING:
    try:
        from ..trace_context import TraceContext
    except ImportError:
        from trace_context import TraceContext


class AgentServiceLoader(LogLoader):
    """
    Agent Service 日志加载器
    
    依赖 conversation_id，需要等 AssistantRuntimeLoader 提取出来后才能执行
    """
    
    @property
    def name(self) -> str:
        return "agent_service"
    
    @property
    def index_pattern(self) -> str:
        return "*:*-logs-air_agent_service-*"
    
    @property
    def depends_on(self) -> list:
        """依赖 conversation_id"""
        return ["conversation_id"]
    
    def build_query(self, ctx: "TraceContext") -> str:
        """使用 conversationId 查询"""
        return f'conversationId:"{ctx.conversation_id}"'

