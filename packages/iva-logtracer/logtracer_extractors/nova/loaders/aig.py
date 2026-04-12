#!/usr/bin/env python3
"""
Nova AIGLoader - AIG 日志加载器

特点:
- 依赖 NCA 日志的 request_id 列表
- 使用 request_id 查询

关联关系:
- NCA.request_id = AIG.request_id (直接匹配)
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


class AIGLoader(LogLoader):
    """
    AIG 日志加载器

    从 NCA 日志中提取 request_id 列表，用于查询对应的 AIG 日志
    """

    @property
    def name(self) -> str:
        return "aig"

    @property
    def index_pattern(self) -> str:
        return "*:*-logs-aig-*"

    @property
    def depends_on_any(self) -> list:
        """依赖 NCA 日志或隐藏 request_id 预取结果。"""
        return ["prefetched_request_ids.nca", "logs.nca"]

    def build_query(self, ctx: "TraceContextProtocol") -> str:
        """
        从 NCA 日志中提取 request_id 列表，用于查询 AIG

        NCA.request_id = AIG.request_id (直接匹配)
        """
        request_ids = ctx.get_prefetched_request_ids("nca")
        if not request_ids:
            request_ids = NCALoader.extract_request_ids_from_logs(ctx.logs.get("nca", []))
        if not request_ids:
            return ""

        # 构建 OR 查询
        if len(request_ids) == 1:
            return f'request_id:"{request_ids[0]}"'

        # 多个 request_id 用 OR 连接
        query_parts = [f'"{rid}"' for rid in request_ids]
        return f'request_id:({" OR ".join(query_parts)})'
