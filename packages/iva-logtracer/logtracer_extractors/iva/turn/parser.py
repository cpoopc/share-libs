#!/usr/bin/env python3
"""
IVA Voice Call Log Analyzer - 日志解析器

将非结构化日志转化为结构化 LogEntry。
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from .models import CallState, EventType, LogEntry, parse_timestamp
from .patterns import KEY_EVENT_PATTERNS, STATE_PATTERN, USER_INPUT_PATTERN


class LogParser:
    """日志解析器 - 将非结构化日志转化为结构化 LogEntry"""

    def __init__(self):
        # 编译正则表达式以提高性能
        self._compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), event_type)
            for pattern, event_type in KEY_EVENT_PATTERNS
        ]
        self._state_pattern = re.compile(STATE_PATTERN)

    def parse_logs(self, raw_logs: List[Dict[str, Any]], session_start: Optional[datetime] = None) -> List[LogEntry]:
        """解析原始日志列表"""
        entries = []

        for raw_log in raw_logs:
            entry = self._parse_single_log(raw_log, session_start)
            if entry:
                entries.append(entry)

        # 按时间排序
        entries.sort(key=lambda x: x.timestamp_dt or datetime.min)

        # 如果没有提供 session_start，使用第一条日志的时间
        if entries and not session_start:
            session_start = entries[0].timestamp_dt
            for entry in entries:
                if entry.timestamp_dt and session_start:
                    entry.timestamp_ms = (entry.timestamp_dt - session_start).total_seconds() * 1000

        return entries

    def _parse_single_log(self, raw_log: Dict[str, Any], session_start: Optional[datetime]) -> Optional[LogEntry]:
        """解析单条日志"""
        ts_str = raw_log.get("@timestamp", "")
        message = raw_log.get("message", "")

        if not ts_str or not message:
            return None

        ts_dt = parse_timestamp(ts_str)

        # 计算相对时间
        timestamp_ms = 0.0
        if ts_dt and session_start:
            timestamp_ms = (ts_dt - session_start).total_seconds() * 1000

        # 提取状态
        state = self._extract_state(message)

        # 确定事件类型
        event_type = self._get_event_type(message)

        # 确定日志级别
        level = self._get_log_level(message, event_type)

        # 推断组件
        component = self._infer_component(message, state)

        # 提取额外数据
        extracted_data = self._extract_data(message)

        return LogEntry(
            raw_line=message,
            timestamp_str=ts_str,
            timestamp_dt=ts_dt,
            timestamp_ms=timestamp_ms,
            level=level,
            state=state,
            event_type=event_type,
            message=message,
            component=component,
            extracted_data=extracted_data,
        )

    def _extract_state(self, message: str) -> Optional[CallState]:
        """从日志消息中提取状态"""
        match = self._state_pattern.search(message)
        if match:
            state_str = match.group(1)
            try:
                return CallState(state_str)
            except ValueError:
                return CallState.UNKNOWN
        return None

    def _get_event_type(self, message: str) -> EventType:
        """获取事件类型"""
        for pattern, event_type in self._compiled_patterns:
            if pattern.search(message):
                return event_type
        return EventType.LOG

    def _get_log_level(self, message: str, event_type: EventType) -> str:
        """获取日志级别"""
        if event_type == EventType.ERROR:
            return "ERROR"
        elif event_type == EventType.WARNING:
            return "WARN"
        elif "error" in message.lower():
            return "ERROR"
        elif "warn" in message.lower():
            return "WARN"
        return "INFO"

    def _infer_component(self, message: str, state: Optional[CallState]) -> str:
        """推断日志来源组件"""
        if "Received generate" in message or "Sending request" in message:
            return "RemoteController"
        elif "Saying phrase" in message or "Phrase has been" in message:
            return "TTS"
        elif "transcript" in message.lower():
            return "SRS"
        elif state:
            return "CallFSM"
        return "Unknown"

    def _extract_data(self, message: str) -> Dict[str, Any]:
        """从日志消息中提取结构化数据"""
        data = {}

        # 提取 TTFT
        ttft_match = re.search(r"Observed TTFT.*?(\d+)ms", message)
        if ttft_match:
            data["ttft_ms"] = int(ttft_match.group(1))

        # 提取 transcript
        transcript_match = re.search(r'"transcript":"([^"]*)"', message)
        if transcript_match:
            data["transcript"] = transcript_match.group(1).strip()

        # 提取 confidence
        conf_match = re.search(r'"confidence":([0-9.]+)', message)
        if conf_match:
            data["confidence"] = float(conf_match.group(1))

        # 提取 phrase
        phrase_match = re.search(r'Saying phrase:\s*(.+)$', message)
        if phrase_match:
            data["phrase"] = phrase_match.group(1).strip()

        # 提取 Generating response for
        response_match = re.search(USER_INPUT_PATTERN, message)
        if response_match:
            data["user_input"] = response_match.group(1).strip()

        # 提取终止原因
        if "Conversation close by event" in message:
            reason_match = re.search(r"reason:\s*(.+?)(?:\s*$|,)", message)
            if reason_match:
                data["termination_reason"] = reason_match.group(1).strip()

        return data

