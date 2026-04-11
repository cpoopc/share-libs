#!/usr/bin/env python3
"""
Platform AGWLoader - AGW 日志加载器

特点:
- 使用 request_id 查询
"""

from typing import TYPE_CHECKING

try:
    from ...loaders import LogLoader
except ImportError:
    from loaders import LogLoader

if TYPE_CHECKING:
    from ...loaders import TraceContextProtocol


class AGWLoader(LogLoader):
    """
    AGW 日志加载器
    """
    
    @property
    def name(self) -> str:
        return "agw"
    
    @property
    def index_pattern(self) -> str:
        return "*:*-logs-agw-*"
    
    @property
    def depends_on(self) -> list:
        """依赖 request_id"""
        return ["request_id"]
    
    def build_query(self, ctx: "TraceContextProtocol") -> str:
        """使用 request_id 查询"""
        return f'request_id:"{ctx.request_id}"'

