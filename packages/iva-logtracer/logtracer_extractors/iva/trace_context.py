#!/usr/bin/env python3
"""
IVA TraceContext - IVA 会话追踪上下文

存储用户输入、派生数据和日志结果的共享上下文
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class TraceContext:
    """
    追踪上下文 - 存储用户输入和派生数据

    用户输入:
        - session_id: 会话 ID (s-xxx 格式)
        - conversation_id: 对话 ID (UUID 格式)
        - account_id: Account ID (用于查询某账户的最近日志)
        - time_range: 时间范围 (如 '24h', '7d')
        - enabled_loaders: 启用的加载器名称集合
        - size: 每个组件返回的最大日志条数

    派生数据 (由 loaders 填充):
        - srs_session_id: SRS Session ID (从 assistant_runtime 日志提取)
        - sgs_session_id: SGS Session ID (从 assistant_runtime 日志提取)

    日志存储:
        - logs: 按组件名称分组的日志
    """

    # ==================== 用户输入 ====================
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    account_id: Optional[str] = None
    time_range: Optional[str] = None
    enabled_loaders: Set[str] = field(default_factory=set)
    size: int = 10000

    # ==================== 派生数据 ====================
    srs_session_id: Optional[str] = None
    sgs_session_id: Optional[str] = None

    # ==================== 日志存储 ====================
    logs: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    component_coverage: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # ==================== 辅助方法 ====================
    
    def _check_key(self, key: str) -> bool:
        """
        检查单个 key 是否有值

        支持嵌套路径，如 'logs.nca' 表示 self.logs['nca'] 非空
        """
        if "." in key:
            # 嵌套路径
            parts = key.split(".", 1)
            parent = getattr(self, parts[0], None)
            if parent is None:
                return False
            if isinstance(parent, dict):
                value = parent.get(parts[1])
                # 对于 logs，检查列表非空
                if isinstance(value, list):
                    return len(value) > 0
                return value is not None
            return False
        return getattr(self, key, None) is not None

    def has(self, *keys: str) -> bool:
        """
        检查是否具有指定的 context 属性（非 None/非空）

        支持嵌套路径，如 'logs.nca' 表示 self.logs['nca'] 非空
        """
        return all(self._check_key(k) for k in keys)

    def has_any(self, *keys: str) -> bool:
        """
        检查是否具有任意一个指定的 context 属性（非 None/非空）

        支持嵌套路径，如 'logs.nca' 表示 self.logs['nca'] 非空
        """
        return any(self._check_key(k) for k in keys)
    
    def is_loader_enabled(self, loader_name: str) -> bool:
        """检查指定的 loader 是否启用"""
        if not self.enabled_loaders:
            return True  # 空集合表示启用所有
        return loader_name in self.enabled_loaders
    
    def get_summary(self) -> Dict[str, int]:
        """获取日志统计摘要"""
        return {name: len(logs) for name, logs in self.logs.items()}
    
    def get_total_logs(self) -> int:
        """获取总日志条数"""
        return sum(len(logs) for logs in self.logs.values())
    
    def to_result(self) -> Dict[str, Any]:
        """转换为结果字典（兼容旧 API）"""
        result = {
            "session_id": self.session_id,
            "conversation_id": self.conversation_id,
            "srs_session_id": self.srs_session_id,
            "sgs_session_id": self.sgs_session_id,
            "logs": self.logs,
            "summary": self.get_summary(),
        }
        if self.account_id:
            result["account_id"] = self.account_id
        if self.component_coverage:
            result["component_coverage"] = self.component_coverage
        return result
