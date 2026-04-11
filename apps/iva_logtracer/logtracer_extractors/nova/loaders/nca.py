#!/usr/bin/env python3
"""
Nova NCALoader - NCA 日志加载器

特点:
- 依赖 conversation_id
- 使用 conversation_id 字段查询（下划线格式）
"""

from typing import TYPE_CHECKING

try:
    from ...loaders import LogLoader
except ImportError:
    from loaders import LogLoader

if TYPE_CHECKING:
    from ...loaders import TraceContextProtocol


class NCALoader(LogLoader):
    """
    NCA 日志加载器
    
    依赖 conversation_id，使用下划线格式的字段名
    """
    
    @property
    def name(self) -> str:
        return "nca"
    
    @property
    def index_pattern(self) -> str:
        return "*:*-logs-nca-*"
    
    @property
    def depends_on(self) -> list:
        """依赖 conversation_id"""
        return ["conversation_id"]
    
    def build_query(self, ctx: "TraceContextProtocol") -> str:
        """使用 conversation_id 查询（注意是下划线格式）"""
        return f'conversation_id:"{ctx.conversation_id}"'

