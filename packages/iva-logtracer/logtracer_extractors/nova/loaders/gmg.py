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
except ImportError:
    from loaders import LogLoader

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
    def depends_on(self) -> list:
        """依赖 NCA 日志"""
        return ["logs.nca"]

    def build_query(self, ctx: "TraceContextProtocol") -> str:
        """
        从 NCA 日志中提取 request_id 列表，用于查询 GMG

        GMG 的 log_context_RCRequestId = NCA 的 request_id
        """
        nca_logs = ctx.logs.get("nca", [])
        if not nca_logs:
            return ""

        # 提取所有 NCA 的 request_id
        request_ids = set()
        for log in nca_logs:
            rid = log.get("request_id", "")
            if rid:
                request_ids.add(rid)

        if not request_ids:
            return ""

        # 构建 OR 查询
        if len(request_ids) == 1:
            return f'log_context_RCRequestId:"{list(request_ids)[0]}"'

        # 多个 request_id 用 OR 连接
        query_parts = [f'"{rid}"' for rid in request_ids]
        return f'log_context_RCRequestId:({" OR ".join(query_parts)})'

