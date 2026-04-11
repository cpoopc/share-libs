#!/usr/bin/env python3
"""
IVA Shared Module - 共享工具和定義

提供跨模組共用的功能：
- timestamp: 時間戳解析工具
- log_normalizer: 日誌字段標準化
- event_registry: 統一事件定義 (Single Source of Truth)
"""

from .log_normalizer import LogEntry, normalize_log_entry
from .timestamp import calculate_duration_ms, format_timestamp, parse_timestamp

__all__ = [
    # Timestamp utilities
    'parse_timestamp',
    'format_timestamp',
    'calculate_duration_ms',
    # Log normalizer
    'normalize_log_entry',
    'LogEntry',
]

