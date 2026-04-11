#!/usr/bin/env python3
"""
Log Normalizer - 日誌字段標準化

統一不同來源日誌的字段命名，提供標準化的日誌結構。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LogEntry:
    """標準化的日誌條目"""
    timestamp: str
    level: str
    message: str
    component: str
    logger: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
    
    # 可選的額外字段
    state: Optional[str] = None
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], component: str = "") -> 'LogEntry':
        """從字典創建標準化日誌條目"""
        normalized = normalize_log_entry(data, component)
        return cls(
            timestamp=normalized['timestamp'],
            level=normalized['level'],
            message=normalized['message'],
            component=normalized['component'],
            logger=normalized['logger'],
            raw=data,
            state=normalized.get('state'),
            session_id=normalized.get('session_id'),
            conversation_id=normalized.get('conversation_id'),
        )


def normalize_log_entry(log: Dict[str, Any], component: str = "") -> Dict[str, Any]:
    """
    標準化日誌字段名稱
    
    處理不同來源的字段命名差異：
    - @timestamp vs timestamp
    - level vs log_level vs severity
    - logger vs logger_name
    
    Args:
        log: 原始日誌字典
        component: 組件名稱（如果未在日誌中指定）
        
    Returns:
        標準化後的日誌字典
    """
    return {
        # 時間戳 - 多個可能的字段名
        'timestamp': (
            log.get('@timestamp') or 
            log.get('timestamp') or 
            log.get('time') or 
            ''
        ),
        
        # 日誌級別
        'level': _normalize_level(
            log.get('level') or 
            log.get('log_level') or 
            log.get('severity') or 
            'INFO'
        ),
        
        # 消息內容
        'message': log.get('message') or log.get('msg') or '',
        
        # 組件
        'component': (
            log.get('component') or 
            log.get('service') or 
            log.get('app') or 
            component or 
            'unknown'
        ),
        
        # Logger 名稱
        'logger': (
            log.get('logger') or 
            log.get('logger_name') or 
            log.get('loggerName') or 
            ''
        ),
        
        # 狀態 (AR 特有)
        'state': _extract_state(log),
        
        # 會話標識
        'session_id': (
            log.get('session_id') or 
            log.get('sessionId') or 
            log.get('session-id')
        ),
        'conversation_id': (
            log.get('conversation_id') or 
            log.get('conversationId') or 
            log.get('conversation-id')
        ),
    }


def _normalize_level(level: str) -> str:
    """標準化日誌級別"""
    level = str(level).upper().strip()
    
    # 處理變體
    level_map = {
        'WARNING': 'WARN',
        'ERR': 'ERROR',
        'CRITICAL': 'FATAL',
        'SEVERE': 'ERROR',
        'TRACE': 'DEBUG',
    }
    
    return level_map.get(level, level)


def _extract_state(log: Dict[str, Any]) -> Optional[str]:
    """從日誌中提取狀態信息"""
    import re
    
    # 直接字段
    if 'state' in log:
        return log['state']
    
    # 從 message 中提取 [state: xxx]
    message = log.get('message', '')
    match = re.search(r'\[state:\s*(\w+(?:-\w+)*)\]', message)
    if match:
        return match.group(1)
    
    return None


def normalize_logs(logs: List[Dict[str, Any]], component: str = "") -> List[Dict[str, Any]]:
    """
    批量標準化日誌列表
    
    Args:
        logs: 日誌列表
        component: 組件名稱
        
    Returns:
        標準化後的日誌列表
    """
    return [normalize_log_entry(log, component) for log in logs]

