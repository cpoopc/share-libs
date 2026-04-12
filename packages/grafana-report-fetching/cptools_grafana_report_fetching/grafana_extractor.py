"""
Grafana Data Extractor
从 Grafana Dashboards 提取指标数据
"""

from typing import Any

from .grafana_utils import GrafanaClient, get_grafana_client


class GrafanaExtractor:
    """Grafana 数据提取器"""

    def __init__(self, source_config: dict[str, Any] | None = None):
        """
        初始化提取器
        
        Args:
            source_config: Grafana 源配置，包含 source_id
        """
        self.source_config = source_config or {}
        self._client: GrafanaClient | None = None

    @property
    def client(self) -> GrafanaClient:
        """延迟初始化 Grafana 客户端"""
        if self._client is None:
            self._client = get_grafana_client(self.source_config)
        return self._client

    def extract_panel(
        self,
        dashboard_uid: str,
        panel_id: int,
        time_from: str = "now-7d",
        time_to: str = "now",
        variables: dict[str, Any] | None = None,
        target_ref_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        从 Panel 提取数据
        
        Args:
            dashboard_uid: Dashboard UID
            panel_id: Panel ID
            time_from: 开始时间
            time_to: 结束时间
            variables: 变量替换
            target_ref_id: 仅提取指定 RefId 的数据
            
        Returns:
            数据点列表
        """
        data = self.client.get_panel_data(
            dashboard_uid=dashboard_uid,
            panel_id=panel_id,
            time_from=time_from,
            time_to=time_to,
            variables=variables or {},
        )
        
        if target_ref_id:
            # Filter by refId
            filtered = [d for d in data if d.get("refId") == target_ref_id]
            return filtered
            
        return data

    def extract_custom_query(
        self,
        expr: str,
        time_from: str = "now-7d",
        time_to: str = "now",
        variables: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        使用自定义 PromQL 表达式提取数据
        
        Args:
            expr: PromQL 表达式
            time_from: 开始时间
            time_to: 结束时间
            variables: 变量替换
            
        Returns:
            数据点列表
        """
        return self.client.query_custom(
            expr=expr,
            time_from=time_from,
            time_to=time_to,
            variables=variables or {},
        )

    def extract_section(
        self,
        section_config: dict[str, Any],
        grafana_sources: dict[str, Any],
        time_from: str | None = None,
        time_to: str | None = None,
    ) -> dict[str, Any]:
        """
        提取整个 Section (call_health, accuracy, latency 等) 的数据
        
        Args:
            section_config: Section 配置
            grafana_sources: Grafana 源定义
            time_from: 覆盖开始时间
            time_to: 覆盖结束时间
            
        Returns:
            {metric_name: result_dict} 字典
        """
        source_key = section_config.get("source")
        source_config = grafana_sources.get(source_key, {})
        
        # 更新客户端
        self.source_config = source_config
        self._client = None  # 重置以重新初始化
        
        dashboard_uid = section_config.get("dashboard_uid", "")
        time_from = time_from or section_config.get("time_from", "now-7d")
        time_to = time_to or section_config.get("time_to", "now")
        variables = section_config.get("variables", {})
        
        results = {}
        panels = section_config.get("panels", [])

        for panel_config in panels:
            name = panel_config.get("name", "Unknown")
            panel_id = panel_config.get("panel_id")
            custom_query = panel_config.get("custom_query")
            ref_id = panel_config.get("ref_id")
            fmt = panel_config.get("format", "percent")

            if panel_id is None and not custom_query:
                print(f"⚠️  {name}: No panel_id or custom_query")
                continue

            try:
                if custom_query:
                    print(f"📈 Extracting: {name} (Custom Query)")
                    data = self.extract_custom_query(
                        expr=custom_query,
                        time_from=time_from,
                        time_to=time_to,
                        variables=variables,
                    )
                else:
                    ref_msg = f" RefId: {ref_id}" if ref_id else ""
                    print(f"📈 Extracting: {name} (Panel ID: {panel_id}{ref_msg})")
                    data = self.extract_panel(
                        dashboard_uid=dashboard_uid,
                        panel_id=panel_id,
                        time_from=time_from,
                        time_to=time_to,
                        variables=variables,
                        target_ref_id=ref_id,
                    )

                result = {
                    "data": data,
                    "panel_id": panel_id,
                    "custom_query": custom_query,
                    "format": fmt,
                    "description": panel_config.get("description", ""),
                }

                if data:
                    values = [r.get("value") for r in data if r.get("value") is not None]
                    if values:
                        result["value"] = sum(values) / len(values)
                        result["min"] = min(values)
                        result["max"] = max(values)
                        print(f"   ✅ Avg: {self._format_value(result['value'], fmt)}, Points: {len(data)}")

                results[name] = result

            except Exception as e:
                print(f"   ❌ Error: {e}")
                results[name] = {"data": [], "error": str(e), "format": fmt}

        return results

    def extract_multiple(
        self,
        config: list[dict[str, Any]],
        grafana_sources: dict[str, Any],
        time_from: str | None = None,
        time_to: str | None = None,
    ) -> dict[str, Any]:
        """
        批量提取多个 Dashboard Section 的数据
        
        Args:
            config: 配置列表
            grafana_sources: 所有可用的 Grafana 源
            time_from: 覆盖开始时间
            time_to: 覆盖结束时间
            
        Returns:
            {metric_name: result_dict} 字典
        """
        all_results = {}
        
        for section_config in config:
            name = section_config.get("name", "unknown_section")
            print(f"📋 Processing Grafana Section: {name}")
            
            section_results = self.extract_section(
                section_config=section_config,
                grafana_sources=grafana_sources,
                time_from=time_from,
                time_to=time_to
            )
            all_results.update(section_results)
            
        return all_results

    @staticmethod
    def _format_value(value: float, fmt: str) -> str:
        """格式化数值"""
        if fmt == "duration":
            if value < 1:
                return f"{value * 1000:.0f}ms"
            return f"{value:.2f}s"
        elif fmt == "percent":
            return f"{value:.2f}%"
        return f"{value:.2f}"
