#!/usr/bin/env python3
"""
IVA CPRC Loaders - CPRC 日志加载器

特点:
- CPRCSRSLoader: 依赖 srs_session_id
- CPRCSGSLoader: 依赖 sgs_session_id
- 通过 message 包含 session_id 的方式搜索
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


class CPRCSRSLoader(LogLoader):
    """
    CPRC SRS 日志加载器
    
    依赖 srs_session_id（Speech Recognition Service）
    """
    
    @property
    def name(self) -> str:
        return "cprc_srs"
    
    @property
    def index_pattern(self) -> str:
        return "*:*-ai-cprc*"
    
    @property
    def depends_on(self) -> list:
        """依赖 srs_session_id"""
        return ["srs_session_id"]
    
    def build_query(self, ctx: "TraceContext") -> str:
        """通过 message 包含 srs_session_id 搜索"""
        return f'message:"{ctx.srs_session_id}"'


class CPRCSGSLoader(LogLoader):
    """
    CPRC SGS 日志加载器
    
    依赖 sgs_session_id（Speech Generation Service）
    """
    
    @property
    def name(self) -> str:
        return "cprc_sgs"
    
    @property
    def index_pattern(self) -> str:
        return "*:*-ai-cprc*"
    
    @property
    def depends_on(self) -> list:
        """依赖 sgs_session_id"""
        return ["sgs_session_id"]
    
    def build_query(self, ctx: "TraceContext") -> str:
        """通过 message 包含 sgs_session_id 搜索"""
        return f'message:"{ctx.sgs_session_id}"'

