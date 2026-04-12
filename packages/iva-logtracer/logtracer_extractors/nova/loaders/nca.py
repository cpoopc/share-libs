#!/usr/bin/env python3
"""
Nova NCALoader - NCA 日志加载器

特点:
- 依赖 conversation_id
- 使用 conversation_id 字段查询（下划线格式）
"""

import sys
from typing import TYPE_CHECKING, Any

try:
    from ...loaders import LogLoader
    from ...kibana_client import parse_time_range
except ImportError:
    from loaders import LogLoader
    from kibana_client import parse_time_range

if TYPE_CHECKING:
    from ...loaders import TraceContextProtocol


class NCALoader(LogLoader):
    """
    NCA 日志加载器
    
    依赖 conversation_id，使用下划线格式的字段名
    """
    
    MIN_DOWNSTREAM_CORRELATION_SIZE = 500
    DOWNSTREAM_NOVA_LOADERS = ("aig", "gmg")

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

    def _should_expand_for_downstream_correlation(self, ctx: "TraceContextProtocol") -> bool:
        if not ctx.conversation_id:
            return False
        return any(ctx.is_loader_enabled(loader_name) for loader_name in self.DOWNSTREAM_NOVA_LOADERS)

    def _get_effective_size(self, ctx: "TraceContextProtocol") -> int:
        if self._should_expand_for_downstream_correlation(ctx):
            return max(ctx.size, self.MIN_DOWNSTREAM_CORRELATION_SIZE)
        return ctx.size

    def load(self, ctx: "TraceContextProtocol", client: Any) -> None:
        """对 Nova 下游链路放宽内部 NCA 拉取量，避免 request_id 采样截断。"""
        query = self.build_query(ctx)

        start_time = None
        end_time = None
        if ctx.time_range:
            start_time = parse_time_range(ctx.time_range)
            end_time = "now"

        try:
            result = client.search(
                query=query,
                index=self.index_pattern,
                start_time=start_time,
                end_time=end_time,
                size=self._get_effective_size(ctx),
            )
            hits = result.get("hits", {}).get("hits", [])
            logs = [hit.get("_source", {}) for hit in hits]

            ctx.logs[self.name] = logs
            print(f"   📊 {self.name}: {len(logs)} logs")

        except Exception as e:
            print(f"   ⚠️  Error loading {self.name}: {e}", file=sys.stderr)
            ctx.logs[self.name] = []
