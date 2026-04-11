#!/usr/bin/env python3
"""
Kibana Log Searcher
Search and format Kibana/Elasticsearch logs.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .client import KibanaClient, KibanaConfig
from .query import parse_time_range


class LogSearcher:
    """Search and display Kibana logs"""
    
    def __init__(
        self,
        client: KibanaClient,
        time_field: str = "@timestamp",
        display_fields: Optional[List[str]] = None,
    ):
        self.client = client
        self.time_field = time_field
        self.display_fields = display_fields or ["@timestamp", "level", "message"]
    
    def search(
        self,
        query: str,
        index: Optional[str] = None,
        last: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        size: int = 100,
        smart_fallback: bool = False,
    ) -> Dict[str, Any]:
        """
        搜索日志

        Args:
            query: Lucene/KQL 查询
            index: 索引模式
            last: 最近时间范围，如 '1h', '30m'
            start_time: 开始时间
            end_time: 结束时间
            size: 返回条数
            smart_fallback: 是否启用智能回退（当字段搜索无结果时回退到全文搜索）

        Returns:
            搜索结果
        """
        # 处理时间范围
        if last:
            start_time = parse_time_range(last)
            end_time = "now"

        if smart_fallback:
            return self.client.smart_search(
                query=query,
                index=index,
                time_field=self.time_field,
                start_time=start_time,
                end_time=end_time,
                size=size,
                fallback_to_fulltext=True,
            )

        return self.client.search(
            query=query,
            index=index,
            time_field=self.time_field,
            start_time=start_time,
            end_time=end_time,
            size=size,
        )
    
    def format_table(self, result: Dict[str, Any], max_width: int = 80) -> str:
        """
        格式化为表格

        Args:
            result: 搜索结果
            max_width: message 字段最大宽度

        Returns:
            格式化的表格字符串
        """
        hits = result.get("hits", {}).get("hits", [])
        meta = result.get("_meta", {})

        if not hits:
            return "No results found."

        lines = []

        # 显示回退信息
        if meta.get("fallback_used"):
            lines.append(f"⚠️  Field query returned no results, using fulltext search")
            lines.append(f"   Original: {meta.get('original_query')}")
            lines.append(f"   Used: {meta.get('used_query')}")
            lines.append("")

        # 表头
        header = " | ".join(f"{f:20}" if f != "message" else f"{f:{max_width}}"
                          for f in self.display_fields)
        lines.append(header)
        lines.append("-" * len(header))

        # 数据行
        for hit in hits:
            source = hit.get("_source", {})
            row_values = []

            for field in self.display_fields:
                value = self._get_nested_field(source, field)
                if field == "message":
                    # 截断长消息
                    value = str(value)[:max_width]
                else:
                    value = str(value)[:20]

                if field == "message":
                    row_values.append(f"{value:{max_width}}")
                else:
                    row_values.append(f"{value:20}")

            lines.append(" | ".join(row_values))

        total = result.get("hits", {}).get("total", {})
        if isinstance(total, dict):
            total_count = total.get("value", 0)
        else:
            total_count = total

        lines.append("")
        lines.append(f"Total: {total_count} hits (showing {len(hits)})")

        return "\n".join(lines)
    
    def format_json(self, result: Dict[str, Any], pretty: bool = True) -> str:
        """格式化为 JSON"""
        hits = result.get("hits", {}).get("hits", [])
        documents = [hit.get("_source", {}) for hit in hits]
        
        if pretty:
            return json.dumps(documents, indent=2, ensure_ascii=False, default=str)
        return json.dumps(documents, ensure_ascii=False, default=str)
    
    def format_markdown(self, result: Dict[str, Any]) -> str:
        """格式化为 Markdown"""
        hits = result.get("hits", {}).get("hits", [])
        if not hits:
            return "No results found."
        
        lines = ["# Log Search Results", ""]
        
        total = result.get("hits", {}).get("total", {})
        if isinstance(total, dict):
            total_count = total.get("value", 0)
        else:
            total_count = total
        
        lines.append(f"**Total**: {total_count} hits (showing {len(hits)})")
        lines.append("")
        
        for i, hit in enumerate(hits, 1):
            source = hit.get("_source", {})
            timestamp = self._get_nested_field(source, "@timestamp")
            level = self._get_nested_field(source, "level")
            message = self._get_nested_field(source, "message")
            
            lines.append(f"## {i}. [{level}] {timestamp}")
            lines.append("")
            lines.append(f"```")
            lines.append(str(message))
            lines.append(f"```")
            lines.append("")
        
        return "\n".join(lines)
    
    def _get_nested_field(self, source: Dict[str, Any], field: str) -> Any:
        """获取嵌套字段值"""
        parts = field.split(".")
        value = source
        
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part, "")
            else:
                return ""
        
        return value if value is not None else ""
    
    def export_to_file(
        self,
        result: Dict[str, Any],
        output_path: Path,
        format: str = "json",
    ) -> Path:
        """
        导出结果到文件
        
        Args:
            result: 搜索结果
            output_path: 输出路径
            format: 格式 (json, markdown)
            
        Returns:
            输出文件路径
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if format == "json":
            content = self.format_json(result)
            suffix = ".json"
        elif format == "markdown" or format == "md":
            content = self.format_markdown(result)
            suffix = ".md"
        else:
            content = self.format_json(result)
            suffix = ".json"
        
        # 确保文件有正确后缀
        if not output_path.suffix:
            output_path = output_path.with_suffix(suffix)
        
        output_path.write_text(content, encoding="utf-8")
        return output_path
