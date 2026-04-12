"""
Kibana/Elasticsearch Client
支持 ES 7.x/8.x 版本
支持通过 Kibana 代理访问，使用 Session Cookie 认证（ReadonlyREST）
"""

import http.cookiejar
import json
import os
import re
import ssl
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import quote


@dataclass
class KibanaConfig:
    """Kibana/Elasticsearch 连接配置"""
    
    # Kibana URL
    url: str
    
    # 认证信息
    username: Optional[str] = None
    password: Optional[str] = None
    
    # 默认索引
    default_index: str = "*"
    
    # 连接选项
    verify_certs: bool = True
    timeout: int = 30
    
    @classmethod
    def from_env(cls) -> "KibanaConfig":
        """从环境变量创建配置"""
        return cls(
            url=os.getenv("KIBANA_URL", os.getenv("KIBANA_ES_URL", "http://localhost:5601")),
            username=os.getenv("KIBANA_USERNAME"),
            password=os.getenv("KIBANA_PASSWORD"),
            default_index=os.getenv("KIBANA_INDEX", "*"),
            verify_certs=os.getenv("KIBANA_VERIFY_CERTS", "true").lower() == "true",
            timeout=int(os.getenv("KIBANA_TIMEOUT", "30")),
        )


class KibanaClient:
    """
    Kibana/Elasticsearch API 客户端
    
    通过 Kibana Session Cookie 进行认证 (ReadonlyREST)
    """
    
    def __init__(self, config: KibanaConfig):
        self.config = config
        self._ssl_context: Optional[ssl.SSLContext] = None
        self._cookie_jar = http.cookiejar.CookieJar()
        self._opener: Optional[urllib.request.OpenerDirector] = None
        self._logged_in = False
        self._csrf_token: Optional[str] = None
        self._login_lock = threading.Lock()  # 线程安全锁
    
    @classmethod
    def from_env(cls) -> "KibanaClient":
        """从环境变量创建客户端"""
        return cls(KibanaConfig.from_env())
    
    @property
    def ssl_context(self) -> ssl.SSLContext:
        """获取 SSL 上下文"""
        if self._ssl_context is None:
            self._ssl_context = ssl.create_default_context()
            if not self.config.verify_certs:
                self._ssl_context.check_hostname = False
                self._ssl_context.verify_mode = ssl.CERT_NONE
        return self._ssl_context
    
    @property
    def opener(self) -> urllib.request.OpenerDirector:
        """获取 URL opener（带 cookie 支持）"""
        if self._opener is None:
            cookie_handler = urllib.request.HTTPCookieProcessor(self._cookie_jar)
            https_handler = urllib.request.HTTPSHandler(context=self.ssl_context)
            self._opener = urllib.request.build_opener(cookie_handler, https_handler)
        return self._opener
    
    def _get_csrf_token(self) -> str:
        """从登录 JS 文件获取 CSRF token"""
        base_url = self.config.url.rstrip("/")
        
        # CSRF token 在这个 JS 文件里
        js_url = f"{base_url}/pkp/legacy/web/assets/js/login_tpl_defer.js"
        
        req = urllib.request.Request(js_url)
        
        try:
            response = self.opener.open(req, timeout=self.config.timeout)
            js_content = response.read().decode()
            
            # 查找 CSRF_TOKEN='...'
            match = re.search(r"CSRF_TOKEN='([^']+)'", js_content)
            if match:
                return match.group(1)
            
            raise Exception("CSRF token not found in login JS")
        except Exception as e:
            raise Exception(f"Failed to get CSRF token: {e}")
    
    def _login(self) -> bool:
        """
        通过 ReadonlyREST 登录 API 获取 session

        线程安全：使用锁确保只有一个线程执行登录

        Returns:
            是否登录成功
        """
        # 快速检查（无锁）
        if self._logged_in:
            return True

        # 使用锁确保只有一个线程执行登录
        with self._login_lock:
            # 双重检查：获取锁后再次检查
            if self._logged_in:
                return True

            base_url = self.config.url.rstrip("/")

            # 1. 先访问登录页面获取 session cookies
            login_page_url = f"{base_url}/login"
            req = urllib.request.Request(login_page_url)
            try:
                self.opener.open(req, timeout=self.config.timeout)
            except Exception:
                pass  # 忽略重定向等错误

            # 2. 获取 CSRF token
            self._csrf_token = self._get_csrf_token()

            # 3. 构建 JSON 登录请求
            login_data = json.dumps({
                "username": self.config.username,
                "password": self.config.password,
            }).encode()

            headers = {
                "Content-Type": "application/json;charset=UTF-8",
                "x-csrf-token": self._csrf_token,
                "kbn-xsrf": "true",
            }

            req = urllib.request.Request(login_page_url, data=login_data, headers=headers, method="POST")

            try:
                response = self.opener.open(req, timeout=self.config.timeout)
                json.loads(response.read().decode())
                # 登录成功，cookie 会自动保存
                self._logged_in = True
                return True
            except urllib.error.HTTPError as e:
                error_body = e.read().decode() if e.fp else ""
                try:
                    error_json = json.loads(error_body)
                    msg = error_json.get("message", error_body)
                except:
                    msg = error_body
                raise Exception(f"Login failed: {msg}")
            except Exception as e:
                raise Exception(f"Login failed: {e}")
    
    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        发送 HTTP 请求（通过 Kibana console proxy）
        
        Args:
            method: HTTP 方法 (GET, POST, etc.)
            path: ES API 路径 (如 /_search)
            body: 请求体
        """
        # 确保已登录
        self._login()
        
        base_url = self.config.url.rstrip("/")
        
        # 通过 Kibana 的 console proxy 访问 ES
        es_path = path.lstrip("/")
        url = f"{base_url}/api/console/proxy?path={quote('/' + es_path, safe='')}&method={method}"
        
        # Console proxy 总是用 POST
        http_method = "POST"
        
        headers = {
            "Content-Type": "application/json",
            "kbn-xsrf": "true",
        }
        
        # 添加 CSRF token
        if self._csrf_token:
            headers["x-csrf-token"] = self._csrf_token
        
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method=http_method)
        
        try:
            response = self.opener.open(req, timeout=self.config.timeout)
            return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            raise Exception(f"HTTP {e.code}: {e.reason}\n{error_body}")
        except urllib.error.URLError as e:
            raise Exception(f"Connection error: {e.reason}")
    
    def test_connection(self) -> Dict[str, Any]:
        """
        测试连接
        
        Returns:
            集群信息
        """
        return self._request("GET", "/")
    
    def search(
        self,
        query: str,
        index: Optional[str] = None,
        time_field: str = "@timestamp",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        size: int = 100,
        sort: Optional[List[Dict[str, str]]] = None,
        search_after: Optional[List[Any]] = None,
        source_includes: Optional[List[str]] = None,
        source_excludes: Optional[List[str]] = None,
        track_total_hits: Optional[bool | int] = None,
        terminate_after: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        搜索日志
        """
        index = index or self.config.default_index
        
        # 构建查询体
        body: Dict[str, Any] = {
            "query": {
                "bool": {
                    "must": [],
                    "filter": [],
                }
            },
            "size": size,
        }

        if track_total_hits is not None:
            body["track_total_hits"] = track_total_hits

        if terminate_after is not None:
            body["terminate_after"] = terminate_after
        
        # 添加查询字符串
        if query and query.strip() and query != "*":
            body["query"]["bool"]["must"].append({
                "query_string": {
                    "query": query,
                    "analyze_wildcard": True,
                }
            })
        
        # 添加时间范围
        if start_time or end_time:
            time_range: Dict[str, Any] = {}
            if start_time:
                time_range["gte"] = start_time
            if end_time:
                time_range["lte"] = end_time
            
            body["query"]["bool"]["filter"].append({
                "range": {
                    time_field: time_range
                }
            })
        
        # 排序
        if sort is not None:
            body["sort"] = sort
        else:
            body["sort"] = [{time_field: {"order": "desc"}}]

        if search_after:
            body["search_after"] = search_after
        
        # 字段过滤
        if source_includes or source_excludes:
            body["_source"] = {}
            if source_includes:
                body["_source"]["includes"] = source_includes
            if source_excludes:
                body["_source"]["excludes"] = source_excludes
        
        return self._request("POST", f"{index}/_search", body)
    
    def count(
        self,
        query: str = "*",
        index: Optional[str] = None,
        time_field: str = "@timestamp",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> int:
        """统计匹配的文档数量"""
        index = index or self.config.default_index
        
        body: Dict[str, Any] = {
            "query": {
                "bool": {
                    "must": [],
                    "filter": [],
                }
            }
        }
        
        if query and query.strip() and query != "*":
            body["query"]["bool"]["must"].append({
                "query_string": {
                    "query": query,
                    "analyze_wildcard": True,
                }
            })
        
        if start_time or end_time:
            time_range: Dict[str, Any] = {}
            if start_time:
                time_range["gte"] = start_time
            if end_time:
                time_range["lte"] = end_time
            
            body["query"]["bool"]["filter"].append({
                "range": {
                    time_field: time_range
                }
            })
        
        result = self._request("POST", f"{index}/_count", body)
        return result.get("count", 0)
    
    def get_indices(self, pattern: str = "*") -> List[str]:
        """获取匹配的索引列表"""
        result = self._request("GET", f"_cat/indices/{pattern}?format=json")
        return [idx.get("index", "") for idx in result if isinstance(idx, dict)]

    def resolve_indices(self, pattern: str = "*") -> Dict[str, List[str]]:
        """使用应用友好的 Resolve Index API 解析 index/alias/data stream。"""
        result = self._request("GET", f"_resolve/index/{pattern}")
        return {
            "indices": [
                item.get("name", "")
                for item in result.get("indices", [])
                if isinstance(item, dict) and item.get("name")
            ],
            "aliases": [
                item.get("name", "")
                for item in result.get("aliases", [])
                if isinstance(item, dict) and item.get("name")
            ],
            "data_streams": [
                item.get("name", "")
                for item in result.get("data_streams", [])
                if isinstance(item, dict) and item.get("name")
            ],
        }
    
    def aggregate(
        self,
        query: str = "*",
        index: Optional[str] = None,
        time_field: str = "@timestamp",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        agg_field: str = "_id",
        agg_type: str = "cardinality",
        agg_name: str = "agg_result",
        size: int = 0,
    ) -> Dict[str, Any]:
        """
        执行聚合查询
        
        Args:
            query: 查询字符串
            index: 索引模式
            time_field: 时间字段
            start_time: 开始时间
            end_time: 结束时间
            agg_field: 聚合字段
            agg_type: 聚合类型 (cardinality, terms, avg, sum, max, min 等)
            agg_name: 聚合名称
            size: 返回文档数量（默认 0，只返回聚合结果）
        
        Returns:
            聚合查询结果
        """
        index = index or self.config.default_index
        
        body: Dict[str, Any] = {
            "size": size,
            "query": {
                "bool": {
                    "must": [],
                    "filter": [],
                }
            },
            "aggs": {
                agg_name: {
                    agg_type: {
                        "field": agg_field
                    }
                }
            }
        }
        
        # 添加查询条件
        if query and query.strip() and query != "*":
            body["query"]["bool"]["must"].append({
                "query_string": {
                    "query": query,
                    "analyze_wildcard": True,
                }
            })
        
        # 添加时间范围
        if start_time or end_time:
            time_range: Dict[str, Any] = {}
            if start_time:
                time_range["gte"] = start_time
            if end_time:
                time_range["lte"] = end_time
            
            body["query"]["bool"]["filter"].append({
                "range": {
                    time_field: time_range
                }
            })
        
        return self._request("POST", f"{index}/_search", body)

    def smart_search(
        self,
        query: str,
        index: Optional[str] = None,
        time_field: str = "@timestamp",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        size: int = 100,
        sort: Optional[List[Dict[str, str]]] = None,
        source_includes: Optional[List[str]] = None,
        source_excludes: Optional[List[str]] = None,
        fallback_to_fulltext: bool = True,
    ) -> Dict[str, Any]:
        """
        智能搜索 - 当字段搜索无结果时自动回退到全文搜索

        用于处理用户提供的 ID 可能不是 conversationId 而是其他 ID 的情况。
        例如用户可能提供 completionId，但我们默认把它当作 conversationId 搜索。

        Args:
            query: 查询字符串
            fallback_to_fulltext: 当字段搜索无结果时，是否回退到全文搜索
            其他参数同 search 方法

        Returns:
            包含搜索结果和元数据的字典:
            {
                "hits": {...},
                "_meta": {
                    "original_query": "...",
                    "used_query": "...",
                    "fallback_used": bool
                }
            }
        """
        # 首先尝试原始查询
        result = self.search(
            query=query,
            index=index,
            time_field=time_field,
            start_time=start_time,
            end_time=end_time,
            size=size,
            sort=sort,
            source_includes=source_includes,
            source_excludes=source_excludes,
        )

        total = result.get("hits", {}).get("total", {})
        hit_count = total.get("value", 0) if isinstance(total, dict) else total

        # 如果有结果或不需要回退，直接返回
        if hit_count > 0 or not fallback_to_fulltext:
            result["_meta"] = {
                "original_query": query,
                "used_query": query,
                "fallback_used": False,
            }
            return result

        # 检查查询是否是字段查询格式 (field:"value")
        # 提取引号中的值进行全文搜索
        import re
        field_query_match = re.match(r'^(\w+):"([^"]+)"$', query)

        if not field_query_match:
            # 不是字段查询格式，无法回退
            result["_meta"] = {
                "original_query": query,
                "used_query": query,
                "fallback_used": False,
            }
            return result

        field_name = field_query_match.group(1)
        field_value = field_query_match.group(2)

        # 使用全文搜索回退
        fulltext_query = f'"{field_value}"'
        fallback_result = self.search(
            query=fulltext_query,
            index=index,
            time_field=time_field,
            start_time=start_time,
            end_time=end_time,
            size=size,
            sort=sort,
            source_includes=source_includes,
            source_excludes=source_excludes,
        )

        fallback_result["_meta"] = {
            "original_query": query,
            "used_query": fulltext_query,
            "fallback_used": True,
            "original_field": field_name,
            "search_value": field_value,
        }

        return fallback_result
