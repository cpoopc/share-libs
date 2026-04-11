#!/usr/bin/env python3
"""
Kibana Log Loaders - 日志加载器公共模块

提供 LogLoader 抽象基类，供 IVA、Nova 等模块实现具体加载器
"""

from .base import LogLoader, TraceContextProtocol

__all__ = [
    "LogLoader",
    "TraceContextProtocol",
]

