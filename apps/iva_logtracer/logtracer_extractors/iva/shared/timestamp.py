#!/usr/bin/env python3
"""
Timestamp Utilities - 統一時間戳處理

提供統一的時間戳解析、格式化和計算功能。
"""

from datetime import datetime
from typing import Optional, Union


def parse_timestamp(ts_str: Union[str, datetime, None]) -> Optional[datetime]:
    """
    解析時間戳字符串為 datetime 對象
    
    支持格式:
    - ISO 8601 格式: 2024-01-15T10:30:00.123456Z
    - ISO 8601 帶時區: 2024-01-15T10:30:00.123456+08:00
    - 微秒截斷處理
    
    Args:
        ts_str: 時間戳字符串、datetime 對象或 None
        
    Returns:
        解析後的 datetime 對象，解析失敗返回 None
    """
    if ts_str is None:
        return None
    
    if isinstance(ts_str, datetime):
        return ts_str
    
    if not isinstance(ts_str, str) or not ts_str.strip():
        return None
    
    try:
        ts_str = ts_str.strip()
        # 替換 Z 為 +00:00 (UTC)
        ts_str = ts_str.replace('Z', '+00:00')
        
        # 處理微秒部分 - 截斷到最多6位
        if '.' in ts_str:
            parts = ts_str.split('.')
            if len(parts) == 2:
                frac_and_tz = parts[1]
                
                # 分離小數部分和時區
                if '+' in frac_and_tz:
                    frac, tz = frac_and_tz.split('+', 1)
                    frac = frac[:6].ljust(6, '0')  # 標準化為6位
                    ts_str = f"{parts[0]}.{frac}+{tz}"
                elif '-' in frac_and_tz and len(frac_and_tz) > 6:
                    # 處理負時區 (如 .123-08:00)
                    idx = frac_and_tz.rfind('-')
                    if idx > 0:
                        frac = frac_and_tz[:idx][:6].ljust(6, '0')
                        tz = frac_and_tz[idx+1:]
                        ts_str = f"{parts[0]}.{frac}-{tz}"
                else:
                    frac = frac_and_tz[:6].ljust(6, '0')
                    ts_str = f"{parts[0]}.{frac}"
        
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError, AttributeError):
        return None


def format_timestamp(dt: Optional[datetime], fmt: str = "%Y-%m-%dT%H:%M:%S.%f") -> str:
    """
    格式化 datetime 為字符串
    
    Args:
        dt: datetime 對象
        fmt: 格式化模式，默認 ISO 8601
        
    Returns:
        格式化後的字符串，如果輸入為 None 返回空字符串
    """
    if dt is None:
        return ""
    return dt.strftime(fmt)


def calculate_duration_ms(
    start: Union[str, datetime, None],
    end: Union[str, datetime, None]
) -> Optional[float]:
    """
    計算兩個時間點之間的持續時間（毫秒）
    
    Args:
        start: 開始時間
        end: 結束時間
        
    Returns:
        持續時間（毫秒），如果任一時間無效返回 None
    """
    start_dt = parse_timestamp(start)
    end_dt = parse_timestamp(end)
    
    if start_dt is None or end_dt is None:
        return None
    
    return (end_dt - start_dt).total_seconds() * 1000


def get_relative_ms(
    timestamp: Union[str, datetime, None],
    base: Union[str, datetime, None]
) -> Optional[float]:
    """
    計算相對於基準時間的毫秒偏移
    
    Args:
        timestamp: 目標時間
        base: 基準時間
        
    Returns:
        相對毫秒偏移，如果任一時間無效返回 None
    """
    return calculate_duration_ms(base, timestamp)

