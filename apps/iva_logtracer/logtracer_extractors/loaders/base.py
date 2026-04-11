#!/usr/bin/env python3
"""
LogLoader - 日志加载器抽象基类

定义日志加载器的接口，所有具体加载器都应继承此类
这是一个通用接口，可被 IVA、Nova 等不同模块使用
"""

import sys
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol


class TraceContextProtocol(Protocol):
    """TraceContext 协议 - 定义 LogLoader 需要的 context 接口"""
    time_range: Optional[str]
    size: int
    logs: Dict[str, List[Dict[str, Any]]]
    
    def is_loader_enabled(self, name: str) -> bool: ...
    def has(self, *attrs: str) -> bool: ...
    def has_any(self, *attrs: str) -> bool: ...


class LogLoader(ABC):
    """
    日志加载器基类 (Plugin Interface)
    
    每个加载器负责:
    1. 声明自己的名称和索引模式
    2. 声明依赖的 context 属性
    3. 构建查询语句
    4. 可选的后处理（提取派生数据）
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """组件名称，用于日志存储的 key"""
        pass
    
    @property
    @abstractmethod
    def index_pattern(self) -> str:
        """Kibana 索引模式"""
        pass
    
    @property
    def depends_on(self) -> List[str]:
        """依赖的 context 属性列表（全部满足）"""
        return []
    
    @property
    def depends_on_any(self) -> List[str]:
        """依赖的 context 属性列表（任一满足即可）"""
        return []
    
    def can_load(self, ctx: TraceContextProtocol) -> bool:
        """检查是否满足加载条件"""
        if not ctx.is_loader_enabled(self.name):
            return False
        if self.depends_on and not ctx.has(*self.depends_on):
            return False
        if self.depends_on_any and not ctx.has_any(*self.depends_on_any):
            return False
        return True
    
    @abstractmethod
    def build_query(self, ctx: TraceContextProtocol) -> str:
        """构建 KQL 查询语句"""
        pass
    
    def get_source_includes(self) -> Optional[List[str]]:
        """返回只需要的字段列表（可选优化）"""
        return None
    
    def load(self, ctx: TraceContextProtocol, client: Any) -> None:
        """执行查询并存储日志到 context"""
        try:
            from ..kibana_client import parse_time_range
        except ImportError:
            from kibana_client import parse_time_range

        query = self.build_query(ctx)
        
        start_time = None
        end_time = None
        if ctx.time_range:
            start_time = parse_time_range(ctx.time_range)
            end_time = "now"
        
        try:
            search_params = {
                "query": query,
                "index": self.index_pattern,
                "start_time": start_time,
                "end_time": end_time,
                "size": ctx.size,
            }
            
            source_includes = self.get_source_includes()
            if source_includes:
                search_params["source_includes"] = source_includes
            
            result = client.search(**search_params)
            hits = result.get("hits", {}).get("hits", [])
            logs = [hit.get("_source", {}) for hit in hits]
            
            ctx.logs[self.name] = logs
            print(f"   📊 {self.name}: {len(logs)} logs")
            
        except Exception as e:
            print(f"   ⚠️  Error loading {self.name}: {e}", file=sys.stderr)
            ctx.logs[self.name] = []
    
    def post_load(self, ctx: TraceContextProtocol) -> None:
        """加载后的后处理 - 可提取派生数据到 context"""
        pass

