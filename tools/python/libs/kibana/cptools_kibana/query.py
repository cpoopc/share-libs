"""
查询构建器和时间解析
"""

import re
from datetime import datetime, timedelta
from typing import Optional, Tuple


def parse_time_range(time_str: str) -> str:
    """
    解析时间范围字符串为 Elasticsearch 格式
    
    支持的格式:
    - 相对时间: 1h, 30m, 7d, 2w (小时/分钟/天/周)
    - ISO 格式: 2025-01-08T00:00:00
    - 日期格式: 2025-01-08
    - ES 格式: now-1h (直接返回)
    
    Args:
        time_str: 时间字符串
        
    Returns:
        Elasticsearch 兼容的时间字符串
    """
    if not time_str:
        return ""
    
    time_str = time_str.strip()
    
    # 已经是 ES 格式
    if time_str.startswith("now"):
        return time_str
    
    # 相对时间格式: 1h, 30m, 7d, 2w
    match = re.match(r'^(\d+)([smhdwM])$', time_str)
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        return f"now-{value}{unit}"
    
    # ISO 格式或日期格式，直接返回
    return time_str


def parse_relative_time(time_str: str) -> Optional[datetime]:
    """
    解析相对时间为 datetime 对象
    
    Args:
        time_str: 如 '1h', '30m', '7d'
        
    Returns:
        datetime 对象
    """
    match = re.match(r'^(\d+)([smhdwM])$', time_str.strip())
    if not match:
        return None
    
    value = int(match.group(1))
    unit = match.group(2)
    
    now = datetime.utcnow()
    
    if unit == 's':
        return now - timedelta(seconds=value)
    elif unit == 'm':
        return now - timedelta(minutes=value)
    elif unit == 'h':
        return now - timedelta(hours=value)
    elif unit == 'd':
        return now - timedelta(days=value)
    elif unit == 'w':
        return now - timedelta(weeks=value)
    elif unit == 'M':
        return now - timedelta(days=value * 30)  # 近似
    
    return None


class QueryBuilder:
    """查询构建器，用于构建 Lucene/KQL 查询"""
    
    def __init__(self):
        self.conditions: list = []
    
    def must(self, field: str, value: str) -> "QueryBuilder":
        """添加必须匹配条件"""
        self.conditions.append(f'{field}:"{value}"')
        return self
    
    def must_not(self, field: str, value: str) -> "QueryBuilder":
        """添加必须不匹配条件"""
        self.conditions.append(f'NOT {field}:"{value}"')
        return self
    
    def should(self, field: str, values: list) -> "QueryBuilder":
        """添加或条件"""
        or_clause = " OR ".join(f'{field}:"{v}"' for v in values)
        self.conditions.append(f"({or_clause})")
        return self
    
    def wildcard(self, field: str, pattern: str) -> "QueryBuilder":
        """添加通配符匹配"""
        self.conditions.append(f'{field}:{pattern}')
        return self
    
    def exists(self, field: str) -> "QueryBuilder":
        """字段存在"""
        self.conditions.append(f'_exists_:{field}')
        return self
    
    def range(
        self, 
        field: str, 
        gte: Optional[str] = None, 
        lte: Optional[str] = None
    ) -> "QueryBuilder":
        """范围查询"""
        if gte and lte:
            self.conditions.append(f'{field}:[{gte} TO {lte}]')
        elif gte:
            self.conditions.append(f'{field}:>={gte}')
        elif lte:
            self.conditions.append(f'{field}:<={lte}')
        return self
    
    def raw(self, query: str) -> "QueryBuilder":
        """添加原始查询"""
        self.conditions.append(query)
        return self
    
    def build(self) -> str:
        """构建查询字符串"""
        if not self.conditions:
            return "*"
        return " AND ".join(self.conditions)
    
    def __str__(self) -> str:
        return self.build()


# 预定义常用查询
COMMON_QUERIES = {
    "recent_errors": 'level:ERROR OR level:error OR log.level:ERROR',
    "recent_warnings": 'level:WARN OR level:WARNING OR level:warn',
    "exceptions": 'exception OR stacktrace OR "stack trace" OR traceback',
    "slow_requests": 'duration:>1000 OR response_time:>1000',
}


def get_predefined_query(name: str) -> Optional[str]:
    """
    获取预定义查询
    
    Args:
        name: 查询名称
        
    Returns:
        查询字符串，如果不存在返回 None
    """
    return COMMON_QUERIES.get(name)
