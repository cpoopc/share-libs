#!/usr/bin/env python3
"""
Nova NCALoader - NCA 日志加载器

特点:
- 依赖 conversation_id
- 使用 conversation_id 字段查询（下划线格式）
"""

from typing import TYPE_CHECKING, Iterable, List

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
    
    REQUEST_ID_SOURCE_INCLUDES = ["@timestamp", "request_id", "metadata.request_id"]

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

    def get_request_id_source_includes(self) -> List[str]:
        """返回隐藏 request_id prefetch 所需的最小字段集。"""
        return list(self.REQUEST_ID_SOURCE_INCLUDES)

    @staticmethod
    def extract_request_ids_from_logs(logs: Iterable[dict]) -> List[str]:
        """从 NCA 日志中提取唯一 request_id，保留首次出现顺序。"""
        request_ids: List[str] = []
        seen: set[str] = set()

        for log in logs:
            rid = log.get("request_id") or log.get("metadata", {}).get("request_id")
            if rid and rid not in seen:
                seen.add(rid)
                request_ids.append(rid)

        return request_ids
