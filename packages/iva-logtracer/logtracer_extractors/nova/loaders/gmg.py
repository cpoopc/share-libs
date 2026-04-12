#!/usr/bin/env python3
"""
Nova GMGLoader - GMG 日志加载器

特点:
- 依赖 NCA 日志的 request_id 列表
- 使用 log_context_RCRequestId 关联查询

关联关系:
- NCA.request_id = GMG.log_context_RCRequestId
"""

from typing import TYPE_CHECKING

try:
    from ...loaders import LogLoader
    from .nca import NCALoader
except ImportError:
    from loaders import LogLoader
    from nca import NCALoader

if TYPE_CHECKING:
    from ...loaders import TraceContextProtocol


class GMGLoader(LogLoader):
    """
    GMG 日志加载器

    从 NCA 日志中提取 request_id 列表，用于查询对应的 GMG 日志
    """

    @property
    def name(self) -> str:
        return "gmg"

    @property
    def index_pattern(self) -> str:
        return "*:*-logs-gmg-*"

    @property
    def depends_on_any(self) -> list:
        """依赖 NCA 日志或隐藏 request_id 预取结果。"""
        return ["prefetched_request_ids.nca", "logs.nca"]

    def build_query(self, ctx: "TraceContextProtocol") -> str:
        """
        从 NCA 日志中提取 request_id 列表，用于查询 GMG

        GMG 的 log_context_RCRequestId = NCA 的 request_id
        """
        request_ids = ctx.get_prefetched_request_ids("nca")
        if not request_ids:
            request_ids = NCALoader.extract_request_ids_from_logs(ctx.logs.get("nca", []))
        if not request_ids:
            return ""

        # 构建 OR 查询
        if len(request_ids) == 1:
            return f'log_context_RCRequestId:"{request_ids[0]}"'

        # 多个 request_id 用 OR 连接
        query_parts = [f'"{rid}"' for rid in request_ids]
        return f'log_context_RCRequestId:({" OR ".join(query_parts)})'
