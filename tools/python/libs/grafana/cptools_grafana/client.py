"""
Grafana API Client
支持 Prometheus 数据源
"""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List

import requests


@dataclass
class GrafanaConfig:
    """Grafana 配置"""
    url: str
    api_key: str = ""
    username: str = ""
    password: str = ""
    timeout: int = 30
    source_id: str = ""  # 来源标识，用于日志

    @classmethod
    def from_env(cls, source_id: str = "") -> "GrafanaConfig":
        """从环境变量创建配置

        支持两种命名方式:
        1. 带 source_id: GRAFANA_<SOURCE_ID>_URL, GRAFANA_<SOURCE_ID>_API_KEY, etc.
        2. 默认: GRAFANA_URL, GRAFANA_API_KEY, etc.

        认证优先级: API_KEY > USERNAME/PASSWORD

        Examples:
            # 默认 Grafana
            GRAFANA_URL=https://grafana.example.com
            GRAFANA_API_KEY=xxx

            # 带 source_id (如 "RC")
            GRAFANA_RC_URL=https://grafana.int.ringcentral.com
            GRAFANA_RC_USERNAME=user
            GRAFANA_RC_PASSWORD=pass
        """
        prefix = f"GRAFANA_{source_id.upper()}_" if source_id else "GRAFANA_"

        # 获取 URL (必需)
        url = os.environ.get(f"{prefix}URL")
        if not url and source_id:
            # 如果带 source_id 的没有，尝试默认的
            url = os.environ.get("GRAFANA_URL")

        if not url:
            raise ValueError(f"Missing {prefix}URL environment variable")

        # 获取认证信息 (API Key 优先)
        api_key = os.environ.get(f"{prefix}API_KEY", "")
        username = os.environ.get(f"{prefix}USERNAME", "")
        password = os.environ.get(f"{prefix}PASSWORD", "")

        if not api_key and not (username and password):
            raise ValueError(
                f"Missing authentication for {source_id or 'default'}. "
                f"Set {prefix}API_KEY or {prefix}USERNAME/{prefix}PASSWORD"
            )

        timeout = int(os.environ.get(f"{prefix}TIMEOUT", os.environ.get("GRAFANA_TIMEOUT", "30")))

        return cls(
            url=url,
            api_key=api_key,
            username=username,
            password=password,
            timeout=timeout,
            source_id=source_id,
        )


class GrafanaClient:
    """Grafana API 客户端"""

    def __init__(self, config: GrafanaConfig):
        self.config = config
        self.base_url = config.url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

        # 支持 API Key 或 Basic Auth
        if config.api_key:
            self.session.headers["Authorization"] = f"Bearer {config.api_key}"
        elif config.username and config.password:
            self.session.auth = (config.username, config.password)

    @classmethod
    def from_env(cls, source_id: str = "") -> "GrafanaClient":
        """从环境变量创建客户端

        Args:
            source_id: Grafana 来源标识 (如 "IVA", "RC")
                      对应环境变量 GRAFANA_<SOURCE_ID>_URL 等
        """
        return cls(GrafanaConfig.from_env(source_id))

    def test_connection(self) -> bool:
        """测试连接"""
        try:
            resp = self.session.get(
                f"{self.base_url}/api/health",
                timeout=self.config.timeout,
            )
            if resp.status_code == 200:
                print(f"✅ Connected to Grafana: {self.base_url}")
                return True
            print(f"❌ Connection failed: {resp.status_code}")
            return False
        except requests.exceptions.RequestException as e:
            print(f"❌ Connection error: {e}")
            return False

    def get_dashboard(self, uid: str) -> Dict[str, Any]:
        """获取 Dashboard 定义"""
        resp = self.session.get(
            f"{self.base_url}/api/dashboards/uid/{uid}",
            timeout=self.config.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def list_dashboards(self, query: str = "") -> List[Dict[str, Any]]:
        """列出 Dashboards"""
        params = {"query": query} if query else {}
        resp = self.session.get(
            f"{self.base_url}/api/search",
            params=params,
            timeout=self.config.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def list_panels(
        self,
        dashboard_uid: str,
        pattern: str = None,
        include_queries: bool = False,
    ) -> List[Dict[str, Any]]:
        """列出 Dashboard 中的 Panels

        Args:
            dashboard_uid: Dashboard UID
            pattern: 可选的正则表达式匹配 panel title
            include_queries: 是否包含查询语句

        Returns:
            Panel 列表，包含 id, title, type, datasource, queries (可选)
        """
        import re
        dashboard = self.get_dashboard(dashboard_uid)
        raw_panels = dashboard["dashboard"].get("panels", [])

        # 展开嵌套 panels (row panels)
        all_panels = []
        for p in raw_panels:
            if p.get("type") == "row" and "panels" in p:
                all_panels.extend(p["panels"])
            else:
                all_panels.append(p)

        results = []
        for p in all_panels:
            title = p.get("title", "")

            # 正则匹配
            if pattern:
                if not re.search(pattern, title, re.IGNORECASE):
                    continue

            panel_info = {
                "id": p.get("id"),
                "title": title,
                "type": p.get("type"),
                "datasource": p.get("datasource"),
            }

            # 包含查询语句
            if include_queries:
                queries = []
                for target in p.get("targets", []):
                    query_info = {
                        "refId": target.get("refId", "A"),
                        "legend": target.get("legendFormat", ""),
                    }
                    # Prometheus
                    if "expr" in target:
                        query_info["type"] = "prometheus"
                        query_info["expr"] = target.get("expr", "")
                    # Elasticsearch
                    elif "query" in target:
                        query_info["type"] = "elasticsearch"
                        query_info["query"] = target.get("query", "")
                    queries.append(query_info)
                panel_info["queries"] = queries

            results.append(panel_info)

        return results

    def find_panel(
        self,
        dashboard_uid: str,
        panel_id: int = None,
        pattern: str = None,
    ) -> Dict[str, Any]:
        """查找单个 Panel

        Args:
            dashboard_uid: Dashboard UID
            panel_id: Panel ID (精确匹配)
            pattern: 正则表达式匹配 panel title (返回第一个匹配)

        Returns:
            Panel 信息，包含 queries
        """
        if panel_id is not None:
            panels = self.list_panels(dashboard_uid, include_queries=True)
            for p in panels:
                if p["id"] == panel_id:
                    return p
            raise ValueError(f"Panel ID {panel_id} not found")
        elif pattern:
            panels = self.list_panels(dashboard_uid, pattern=pattern, include_queries=True)
            if panels:
                return panels[0]
            raise ValueError(f"No panel matching pattern '{pattern}'")
        else:
            raise ValueError("Must provide panel_id or pattern")

    def query_prometheus(
        self,
        datasource_uid: str,
        expr: str,
        time_from: str = "now-7d",
        time_to: str = "now",
        step: str = "1h",
    ) -> Dict[str, Any]:
        """执行 Prometheus 查询，自动兼容新旧 Grafana API"""
        now = datetime.now()
        from_ts = self._parse_time(time_from, now)
        to_ts = self._parse_time(time_to, now)

        # 先尝试新版 API (Grafana 8+)
        payload = {
            "queries": [
                {
                    "refId": "A",
                    "datasource": {"type": "prometheus", "uid": datasource_uid},
                    "expr": expr,
                    "interval": step,
                    "intervalMs": self._parse_interval_ms(step),
                    "maxDataPoints": 1000,
                    "range": True,
                    "instant": False,
                }
            ],
            "from": str(int(from_ts.timestamp() * 1000)),
            "to": str(int(to_ts.timestamp() * 1000)),
        }

        resp = self.session.post(
            f"{self.base_url}/api/ds/query",
            json=payload,
            timeout=self.config.timeout,
        )

        if resp.status_code == 404:
            # 回退到旧版 proxy API (Grafana 7 及更早)
            return self._query_prometheus_proxy(datasource_uid, expr, from_ts, to_ts, step)

        resp.raise_for_status()
        return resp.json()

    def _query_prometheus_proxy(
        self,
        datasource_uid: str,
        expr: str,
        from_ts: datetime,
        to_ts: datetime,
        step: str,
    ) -> Dict[str, Any]:
        """使用旧版 Grafana proxy API 查询 Prometheus"""
        # 获取数据源 ID (通过 UID 查找)
        ds_id = self._get_datasource_id(datasource_uid)

        # 使用 range query
        resp = self.session.get(
            f"{self.base_url}/api/datasources/proxy/{ds_id}/api/v1/query_range",
            params={
                "query": expr,
                "start": from_ts.timestamp(),
                "end": to_ts.timestamp(),
                "step": step,
            },
            timeout=self.config.timeout,
        )
        resp.raise_for_status()
        prom_result = resp.json()

        # 转换为新版 API 格式
        return self._convert_prom_to_ds_query_format(prom_result)

    def _get_datasource_id(self, uid: str) -> int:
        """通过 UID 获取数据源 ID"""
        if not hasattr(self, "_ds_cache"):
            self._ds_cache = {}

        if uid in self._ds_cache:
            return self._ds_cache[uid]

        # 获取所有数据源
        resp = self.session.get(f"{self.base_url}/api/datasources")
        resp.raise_for_status()

        for ds in resp.json():
            self._ds_cache[ds.get("uid", "")] = ds.get("id")
            self._ds_cache[ds.get("name", "")] = ds.get("id")

        return self._ds_cache.get(uid, 1)  # 默认返回 1

    def _convert_prom_to_ds_query_format(self, prom_result: Dict[str, Any]) -> Dict[str, Any]:
        """将 Prometheus API 结果转换为 Grafana ds/query 格式"""
        frames = []

        if prom_result.get("status") == "success":
            data = prom_result.get("data", {})
            data.get("resultType", "")
            results = data.get("result", [])

            for item in results:
                metric = item.get("metric", {})
                values = item.get("values", []) or [item.get("value", [])]

                if values:
                    times = [v[0] for v in values if len(v) >= 2]
                    vals = [float(v[1]) if v[1] != "NaN" else None for v in values if len(v) >= 2]

                    frames.append({
                        "schema": {
                            "fields": [
                                {"name": "Time", "type": "time"},
                                {"name": "Value", "type": "number", "labels": metric},
                            ]
                        },
                        "data": {"values": [times, vals]},
                    })

        return {"results": {"A": {"frames": frames}}}

    def query_custom(
        self,
        expr: str,
        time_from: str = "now-7d",
        time_to: str = "now",
        variables: Dict[str, str] = None,
        datasource_uid: str = "prometheus",
    ) -> List[Dict[str, Any]]:
        """
        执行自定义 Prometheus 查询

        Args:
            expr: Prometheus 查询表达式
            time_from: 开始时间
            time_to: 结束时间
            variables: 变量替换
            datasource_uid: 数据源 UID
        """
        # 替换变量
        if variables:
            for var_name, var_value in variables.items():
                expr = expr.replace(f"${var_name}", var_value)
                expr = expr.replace(f"${{{var_name}}}", var_value)

        # 替换内建变量
        expr = self._substitute_builtin_variables(expr, time_from, time_to)

        # 执行查询
        data = self.query_prometheus(
            datasource_uid=datasource_uid,
            expr=expr,
            time_from=time_from,
            time_to=time_to,
        )
        return self._parse_prometheus_result(data, "")

    def get_panel_data(
        self,
        dashboard_uid: str,
        panel_id: int,
        time_from: str = "now-7d",
        time_to: str = "now",
        variables: Dict[str, str] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取指定 Panel 的数据

        Args:
            dashboard_uid: Dashboard UID
            panel_id: Panel ID
            time_from: 开始时间
            time_to: 结束时间
            variables: Dashboard 变量，如 {"namespace": "production", "datasource": "prometheus"}
        """
        dashboard = self.get_dashboard(dashboard_uid)
        panels = dashboard["dashboard"]["panels"]

        # 获取 dashboard 中定义的变量（如 constant 类型的变量）
        all_variables = self._get_dashboard_variables(dashboard)
        if variables:
            all_variables.update(variables)

        # 支持嵌套 panels (row panels)
        all_panels = []
        for p in panels:
            if p.get("type") == "row" and "panels" in p:
                all_panels.extend(p["panels"])
            else:
                all_panels.append(p)

        panel = next((p for p in all_panels if p["id"] == panel_id), None)
        if not panel:
            raise ValueError(f"Panel {panel_id} not found in dashboard {dashboard_uid}")

        # 获取数据源和查询
        ds = panel.get("datasource", {})
        targets = panel.get("targets", [])

        if not targets:
            return []

        # 解析数据源类型和 UID
        ds_type = ds.get("type", "prometheus")
        ds_uid = ds.get("uid", "")

        # 解析变量引用 (如 ${datasource})
        if ds_uid.startswith("${") and ds_uid.endswith("}"):
            var_name = ds_uid[2:-1]
            if all_variables and var_name in all_variables:
                ds_uid = all_variables[var_name]

        # 根据数据源类型选择查询方式
        if ds_type == "elasticsearch":
            return self._query_elasticsearch_panel(
                panel, ds_uid, time_from, time_to, all_variables
            )
        else:
            # Prometheus 查询
            return self._query_prometheus_panel(
                targets, ds_uid, time_from, time_to, all_variables
            )

    def _query_prometheus_panel(
        self,
        targets: List[Dict[str, Any]],
        ds_uid: str,
        time_from: str,
        time_to: str,
        variables: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """执行 Prometheus Panel 查询"""
        results = []
        for target in targets:
            expr = target.get("expr", "")
            if not expr:
                continue

            # 替换查询中的变量
            if variables:
                for var_name, var_value in variables.items():
                    expr = expr.replace(f"${var_name}", var_value)
                    expr = expr.replace(f"${{{var_name}}}", var_value)

            # 替换 Grafana 内建变量
            expr = self._substitute_builtin_variables(expr, time_from, time_to)

            data = self.query_prometheus(
                datasource_uid=ds_uid or "prometheus",
                expr=expr,
                time_from=time_from,
                time_to=time_to,
            )
            results.extend(self._parse_prometheus_result(data, target.get("legendFormat", "")))

        return results

    def _query_elasticsearch_panel(
        self,
        panel: Dict[str, Any],
        ds_uid: str,
        time_from: str,
        time_to: str,
        variables: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """执行 Elasticsearch Panel 查询"""
        targets = panel.get("targets", [])
        if not targets:
            return []

        results = []
        for target in targets:
            query = target.get("query", "")
            if not query or not query.strip():
                continue

            # 替换查询中的变量
            if variables:
                for var_name, var_value in variables.items():
                    # 处理 $__all 变量
                    if var_value == "$__all" or (isinstance(var_value, list) and "$__all" in var_value):
                        query = query.replace(f"${var_name}", "*")
                        query = query.replace(f"${{{var_name}}}", "*")
                    else:
                        query = query.replace(f"${var_name}", str(var_value))
                        query = query.replace(f"${{{var_name}}}", str(var_value))

                        query = query.replace(f"${var_name}", str(var_value))
                        query = query.replace(f"${{{var_name}}}", str(var_value))

            # Fix "auto" interval in bucketAggs which fails in API
            bucket_aggs = target.get("bucketAggs", [])
            for agg in bucket_aggs:
                if agg.get("type") == "date_histogram":
                    settings = agg.get("settings", {})
                    if settings.get("interval") == "auto":
                        settings["interval"] = "1d"

            # Optimization: Replace cardinality with count to avoid specialized aggregation errors
            # and improve stability for simple count metrics
            metrics = target.get("metrics", [])
            for m in metrics:
                if m.get("type") == "cardinality":
                    m["type"] = "count"
                    m.pop("field", None) # Count doesn't need field

            data = self.query_elasticsearch(
                datasource_uid=ds_uid,
                target=target,
                query=query,
                time_from=time_from,
                time_to=time_to,
            )
            results.extend(self._parse_elasticsearch_result(data, target))

        return results

    def query_elasticsearch(
        self,
        datasource_uid: str,
        target: Dict[str, Any],
        query: str,
        time_from: str = "now-7d",
        time_to: str = "now",
    ) -> Dict[str, Any]:
        """执行 Elasticsearch 查询"""
        now = datetime.now()
        from_ts = int(self._parse_time(time_from, now).timestamp() * 1000)
        to_ts = int(self._parse_time(time_to, now).timestamp() * 1000)

        # 构建 Grafana DS Query 请求
        payload = {
            "queries": [
                {
                    "refId": target.get("refId", "A"),
                    "datasource": {"uid": datasource_uid, "type": "elasticsearch"},
                    "query": query,
                    "metrics": target.get("metrics", []),
                    "bucketAggs": target.get("bucketAggs", []),
                    "timeField": target.get("timeField", "@timestamp"),
                }
            ],
            "from": str(from_ts),
            "to": str(to_ts),
        }

        resp = self.session.post(
            f"{self.base_url}/api/ds/query",
            json=payload,
            timeout=self.config.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def _parse_elasticsearch_result(
        self,
        result: Dict[str, Any],
        target: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """解析 Elasticsearch 查询结果"""
        rows = []

        for _key, data in result.get("results", {}).items():
            for frame in data.get("frames", []):
                schema = frame.get("schema", {})
                fields = schema.get("fields", [])
                values = frame.get("data", {}).get("values", [])

                if not values:
                    continue

                # 对于 stat/table panel，Grafana 新旧版本返回的字段类型名称并不稳定。
                # 除了传统的 number/float/double，也可能出现 float64/nullable float64。
                # 这里优先跳过时间字段，然后尽可能把可转成 float 的值收集出来。
                for i, field in enumerate(fields):
                    if i >= len(values):
                        continue

                    f_type = str(field.get("type", "")).lower()
                    f_name = str(field.get("name", "value"))

                    if "time" in f_type or f_name.lower() == "time":
                        continue

                    field_values = values[i]
                    if not field_values:
                        continue

                    parsed_values = []
                    for val in field_values:
                        if val is None or isinstance(val, bool):
                            continue
                        try:
                            parsed_values.append(float(val))
                        except (TypeError, ValueError):
                            continue

                    if not parsed_values:
                        continue

                    for val in parsed_values:
                        rows.append({
                            "metric": f_name,
                            "value": val,
                            "refId": target.get("refId")
                        })

        return rows

    def _get_dashboard_variables(self, dashboard: Dict[str, Any]) -> Dict[str, str]:
        """从 Dashboard 定义中获取变量的默认值"""
        variables = {}
        templating = dashboard.get("dashboard", {}).get("templating", {})

        for var in templating.get("list", []):
            var_name = var.get("name")
            var_type = var.get("type")

            if not var_name:
                continue

            # 常量变量
            if var_type == "constant":
                variables[var_name] = var.get("query", "")
            # 查询变量和其他类型：使用当前值
            elif "current" in var:
                current = var["current"]
                value = current.get("value")
                if isinstance(value, list):
                    # 多值变量，使用第一个值或用 | 连接
                    if len(value) == 1:
                        variables[var_name] = value[0]
                    else:
                        # 多个值用 | 连接（Prometheus 正则格式）
                        variables[var_name] = "|".join(str(v) for v in value if v != "$__all")
                elif value:
                    variables[var_name] = str(value)

        return variables

    def _substitute_builtin_variables(self, expr: str, time_from: str = "now-7d", time_to: str = "now") -> str:
        """替换 Grafana 内建变量"""
        # $__all 表示匹配所有，在 Prometheus 中用 .* 正则
        expr = expr.replace("$__all", ".*")

        # $__rate_interval 是自动计算的 rate 间隔，通常取 scrape_interval 的 4 倍
        # 默认使用 5m 作为安全值
        expr = expr.replace("$__rate_interval", "5m")

        # $__interval 是基于时间范围自动计算的间隔
        expr = expr.replace("$__interval", "1m")

        # $__range 是时间范围，用于 increase() 等函数
        # 计算时间范围并转换为 Prometheus 格式
        range_str = self._calculate_range(time_from, time_to)
        expr = expr.replace("$__range", range_str)

        return expr

    def _calculate_range(self, time_from: str, time_to: str) -> str:
        """计算时间范围并返回 Prometheus duration 格式"""
        now = datetime.now()
        from_ts = self._parse_time(time_from, now)
        to_ts = self._parse_time(time_to, now)

        delta = to_ts - from_ts
        total_seconds = int(delta.total_seconds())

        if total_seconds >= 86400:  # >= 1 day
            days = total_seconds // 86400
            return f"{days}d"
        elif total_seconds >= 3600:  # >= 1 hour
            hours = total_seconds // 3600
            return f"{hours}h"
        elif total_seconds >= 60:  # >= 1 minute
            minutes = total_seconds // 60
            return f"{minutes}m"
        else:
            return f"{total_seconds}s"

    def _parse_time(self, time_str: str, now: datetime) -> datetime:
        """解析 Grafana 时间格式 (now-7d, now-1h, etc.)"""
        if time_str == "now":
            return now

        if time_str.startswith("now-"):
            duration = time_str[4:]
            value = int(duration[:-1])
            unit = duration[-1]

            if unit == "m":
                return now - timedelta(minutes=value)
            elif unit == "h":
                return now - timedelta(hours=value)
            elif unit == "d":
                return now - timedelta(days=value)
            elif unit == "w":
                return now - timedelta(weeks=value)

        # 尝试解析 ISO 格式
        return datetime.fromisoformat(time_str)

    def _parse_interval_ms(self, interval: str) -> int:
        """解析间隔为毫秒"""
        value = int(interval[:-1])
        unit = interval[-1]

        if unit == "s":
            return value * 1000
        elif unit == "m":
            return value * 60 * 1000
        elif unit == "h":
            return value * 3600 * 1000
        elif unit == "d":
            return value * 86400 * 1000

        return 60000  # 默认 1 分钟

    def _parse_prometheus_result(
        self,
        result: Dict[str, Any],
        legend_format: str = "",
    ) -> List[Dict[str, Any]]:
        """解析 Prometheus 查询结果"""
        rows = []

        for _key, data in result.get("results", {}).items():
            for frame in data.get("frames", []):
                schema = frame.get("schema", {})
                fields = schema.get("fields", [])
                values = frame.get("data", {}).get("values", [])

                if not values or len(values) < 2:
                    continue

                # 第一个通常是时间戳，后面是值
                timestamps = values[0]
                data_values = values[1] if len(values) > 1 else []

                # 获取 metric 名称
                metric_name = legend_format
                if not metric_name and len(fields) > 1:
                    labels = fields[1].get("labels", {})
                    metric_name = labels.get("__name__", "value")

                for i, ts in enumerate(timestamps):
                    rows.append({
                        "timestamp": datetime.fromtimestamp(ts / 1000).isoformat(),
                        "metric": metric_name,
                        "value": data_values[i] if i < len(data_values) else None,
                    })

        return rows

    def _substitute_variables(
        self,
        targets: List[Dict],
        variables: Dict[str, str],
    ) -> List[Dict]:
        """替换查询中的 Dashboard 变量"""
        import copy
        import re

        result = copy.deepcopy(targets)

        for target in result:
            expr = target.get("expr", "")
            if not expr:
                continue

            # 替换 $variable 和 ${variable} 格式
            for var_name, var_value in variables.items():
                # $variable
                expr = re.sub(
                    rf'\${var_name}(?![a-zA-Z0-9_])',
                    var_value,
                    expr
                )
                # ${variable}
                expr = expr.replace(f'${{{var_name}}}', var_value)

            target["expr"] = expr

        return result

