#!/usr/bin/env python3
"""
IVA Voice Call Log Analyzer - 语音通话日志分析模块

基于 voice-call-logs-analysis.md 设计，采用模块化架构：
1. Parser (解析器) - 将非结构化日志转化为结构化 LogEntry
2. Sessionizer (会话聚合) - 将日志聚合为 CallSession
3. Analyzer (分析引擎) - 计算 TTFT、统计打断次数、识别错误模式、验证状态机
4. Reporter (报告生成) - 输出统计摘要和时序重建报告

状态机流程:
  init → greeting → after-greeting/listening → answering → listening (循环)
                                                    ↓
                                              cancelling (打断)
                                                    ↓
                                           after-interruption → answering

Turn 定义:
  1. Greeting Turn: User connected → LLM speaking completed
  2. User Turn: Received transcript → LLM speaking completed
  3. Continued Turn: after-interruption → LLM speaking completed (打断后继续)
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .formatters import (
    format_report_markdown,
    format_report_table,
    generate_html_report,
    generate_visualizations,
)

# 从子模块导入
from .models import (
    AnalysisReport,
    CallMetrics,
    CallSession,
    EventType,
    Turn,
    TurnEvent,
    parse_timestamp,
)
from .parser import LogParser
from .patterns import (
    CRITICAL_EVENT_KEYWORDS,
    KEY_EVENT_PATTERNS,
    STATE_PATTERN,
    TURN_END_PATTERNS,
    TURN_START_PATTERNS,
    USER_INPUT_PATTERN,
)

# ============================================================================
# Analyzer - 分析引擎
# ============================================================================

class VoiceCallAnalyzer:
    """语音通话分析器 - 主分析引擎

    集成 Parser, Sessionizer, Analyzer 功能，提供完整的通话分析
    """

    def __init__(self, session_dir: Path):
        """初始化分析器"""
        self.session_dir = Path(session_dir)
        self.logs: Dict[str, List[Dict[str, Any]]] = {}
        self.parser = LogParser()
        self.session: Optional[CallSession] = None
        self._load_trace_files()

    def _load_trace_files(self) -> None:
        """加载所有 trace.json 文件"""
        for trace_file in self.session_dir.glob("*_trace.json"):
            component = trace_file.stem.replace("_trace", "")
            try:
                with open(trace_file, "r", encoding="utf-8") as f:
                    self.logs[component] = json.load(f)
            except Exception as e:
                print(f"⚠️  Error loading {trace_file}: {e}", file=sys.stderr)

    def _load_summary(self) -> Dict[str, Any]:
        """加载 summary.json"""
        summary_file = self.session_dir / "summary.json"
        if summary_file.exists():
            with open(summary_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    @staticmethod
    def _normalize_tool_type(tool_type: Optional[str]) -> str:
        """Normalize tool type markers to client/server/unknown."""
        value = (tool_type or "").strip().lower()
        if value in {"clienttool", "client", "builtin"}:
            return "client"
        if value in {"servertool", "server", "integration"}:
            return "server"
        return "unknown"

    @staticmethod
    def _normalize_tool_status(status: Any) -> str:
        """Normalize tool status values from different components."""
        if isinstance(status, bool):
            return "success" if status else "failed"
        value = str(status or "").strip().lower()
        if value in {"1", "success", "finished", "completed", "ok", "tool_status_success", "true"}:
            return "success"
        if value in {"0", "failed", "failure", "error", "tool_status_failed", "false"}:
            return "failed"
        return value or "unknown"

    def _extract_transcript(self, message: str) -> Tuple[Optional[str], float]:
        """从日志消息中提取用户语音转录"""
        match = re.search(r'"transcript":"([^"]*)"', message)
        transcript = match.group(1).strip() if match else None
        conf_match = re.search(r'"confidence":([0-9.]+)', message)
        confidence = float(conf_match.group(1)) if conf_match else 0.0
        return transcript, confidence

    def _extract_ai_response(self, message: str) -> Optional[str]:
        """从日志消息中提取 AI 响应"""
        match = re.search(r'"content":"([^"]*)"', message)
        if match:
            return match.group(1).replace("\\n", "\n")
        match = re.search(r'Saying phrase: (.+)$', message)
        if match:
            return match.group(1)
        return None

    def _normalize_pairing_key(self, event_name: str, extra_detail: str) -> str:
        """
        Generate normalized pairing key for precise start/end matching.
        
        Examples:
            ('llm_request_start', ' [chitchat]') -> 'llm_request:chitchat'
            ('llm_request_end', ' [Chitchat]') -> 'llm_request:chitchat'
            ('generation_start', ' [Filler, gpt-4]') -> 'generation:filler'
        """
        # Extract base type (remove _start/_end suffix)
        base_type = event_name.replace('_start', '').replace('_end', '')
        
        # Normalize extra_detail: lowercase, remove brackets, take first part
        if extra_detail:
            detail = extra_detail.lower().strip()
            # Remove surrounding brackets
            detail = re.sub(r'^[\s\[\(]+|[\s\]\)]+$', '', detail)
            # Take only first item if comma-separated (e.g., "Chitchat, gpt-4" -> "chitchat")
            detail = detail.split(',')[0].strip()
            # Normalize separators
            detail = detail.replace('-', '').replace('_', '').replace(' ', '')
            
            if detail:
                return f"{base_type}:{detail}"
        
        return base_type

    def _is_turn_start(self, message: str) -> Tuple[bool, str]:
        """检查是否为 Turn 开始"""
        for pattern, event_type in TURN_START_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                return True, event_type
        return False, ""

    def _is_turn_end(self, message: str) -> Tuple[bool, str]:
        """检查是否为 Turn 结束"""
        for pattern, event_type in TURN_END_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                return True, event_type
        return False, ""

    def _get_event_type(self, message: str) -> EventType:
        """获取事件类型"""
        for pattern, event_type in KEY_EVENT_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                return event_type
        return EventType.LOG

    def _extract_state(self, message: str) -> Optional[str]:
        """从日志消息中提取状态"""
        match = re.search(STATE_PATTERN, message)
        return match.group(1) if match else None

    def _is_critical_event(self, message: str) -> bool:
        """检查是否为关键流程事件"""
        return any(keyword in message for keyword in CRITICAL_EVENT_KEYWORDS)

    def analyze(self) -> AnalysisReport:
        """执行完整的语音通话分析

        包括:
        1. Turn 检测和拆分
        2. 性能指标计算 (TTFT, 延迟等)
        3. 异常和错误检测
        4. 状态机流转验证
        5. 关键流程重建
        """
        summary = self._load_summary()

        # 初始化 metrics
        metrics = CallMetrics()

        report = AnalysisReport(
            session_id=summary.get("session_id"),
            conversation_id=summary.get("conversation_id"),
            metrics=metrics,
        )

        # 获取 assistant_runtime 日志
        ar_logs = self.logs.get("assistant_runtime", [])
        if not ar_logs:
            print("⚠️  No assistant_runtime logs found", file=sys.stderr)
            return report

        # 按时间排序
        sorted_logs: List[Tuple[datetime, str, Dict]] = []
        for log in ar_logs:
            ts_str = log.get("@timestamp", "")
            ts = parse_timestamp(ts_str)
            if ts:
                sorted_logs.append((ts, ts_str, log))
        sorted_logs.sort(key=lambda x: x[0])

        # 收集全局指标
        for ts_dt, ts_str, log in sorted_logs:
            message = log.get("message", "")

            # 收集状态
            state = self._extract_state(message)
            if state:
                metrics.states_visited.add(state)

            # 收集 TTFT
            ttft_match = re.search(r"Observed TTFT.*?(\d+)ms", message)
            if ttft_match:
                metrics.ttft_values.append(int(ttft_match.group(1)))

            # 检测打断
            if "Interrupting the generation" in message:
                metrics.interruption_count += 1

            # 检测错误和警告
            if re.search(r"error:|failed|failure|fatal", message, re.IGNORECASE):
                metrics.error_count += 1
                report.errors.append(f"[{ts_str}] {message[:100]}")
            elif re.search(r"warn:|timeout", message, re.IGNORECASE):
                metrics.warning_count += 1
                report.warnings.append(f"[{ts_str}] {message[:100]}")

            # 检测终止原因
            if "Conversation close by event" in message:
                report.is_completed = True
                reason_match = re.search(r"reason:\s*(.+?)(?:\s*$|,)", message)
                if reason_match:
                    report.termination_reason = reason_match.group(1).strip()

        # 计算平均 TTFT
        if metrics.ttft_values:
            metrics.avg_ttft_ms = sum(metrics.ttft_values) / len(metrics.ttft_values)

        # 使用状态机方法检测 Turn
        turns: List[Turn] = []
        current_turn: Optional[Turn] = None
        turn_number = 0

        for ts_dt, ts_str, log in sorted_logs:
            message = log.get("message", "")

            # 提取状态并添加到 Turn
            state = self._extract_state(message)

            # 检测 Turn 开始
            is_start, start_type = self._is_turn_start(message)
            if is_start:
                if start_type == "greeting_start":
                    # Greeting 开始
                    if current_turn:
                        current_turn.end_timestamp = ts_str
                        self._finalize_turn(current_turn, sorted_logs)
                        turns.append(current_turn)

                    turn_number += 1
                    current_turn = Turn(
                        turn_number=turn_number,
                        turn_type="greeting",
                        start_timestamp=ts_str,
                    )
                    continue

                elif start_type == "user_transcript_state":
                    # [state: listening] Received transcript from user
                    # 这是正式的用户输入，应该创建新 Turn
                    if current_turn:
                        # 如果当前 Turn 没有正常结束，标记为被打断
                        if not current_turn.end_timestamp:
                            current_turn.turn_type = current_turn.turn_type + "_interrupted"
                        current_turn.end_timestamp = ts_str
                        self._finalize_turn(current_turn, sorted_logs)
                        turns.append(current_turn)

                    turn_number += 1
                    current_turn = Turn(
                        turn_number=turn_number,
                        turn_type="user_turn",
                        start_timestamp=ts_str,
                    )
                    # 从相关日志中提取 transcript
                    self._extract_user_input(current_turn, ts_dt, sorted_logs)
                    continue

                elif start_type == "after_interruption":
                    # 打断后继续处理 - 这是一个新的 Turn
                    # 不需要结束当前 Turn，因为它已经在 cancelling 状态结束了
                    if current_turn and not current_turn.end_timestamp:
                        # 如果当前 Turn 还没结束，先结束它
                        current_turn.turn_type = current_turn.turn_type + "_interrupted"
                        current_turn.end_timestamp = ts_str
                        self._finalize_turn(current_turn, sorted_logs)
                        turns.append(current_turn)

                    turn_number += 1
                    current_turn = Turn(
                        turn_number=turn_number,
                        turn_type="user_turn_continued",
                        start_timestamp=ts_str,
                    )
                    # 从后续的 "Generating response for:" 日志中提取用户输入
                    self._extract_user_input_from_generating(current_turn, ts_dt, sorted_logs)
                    continue

            # 收集 Turn 内的状态
            if current_turn and state and state not in current_turn.states:
                current_turn.states.append(state)

            # 检测 Turn 结束
            is_end, _ = self._is_turn_end(message)
            if is_end and current_turn:
                current_turn.end_timestamp = ts_str
                self._finalize_turn(current_turn, sorted_logs)
                turns.append(current_turn)
                current_turn = None
                continue

            # 检测打断
            if current_turn and "Interrupting the generation" in message:
                current_turn.was_interrupted = True
                if "_interrupted" not in current_turn.turn_type:
                    current_turn.turn_type = current_turn.turn_type + "_interrupted"

        # 处理最后一个未结束的 Turn
        if current_turn:
            if sorted_logs:
                current_turn.end_timestamp = sorted_logs[-1][1]
            self._finalize_turn(current_turn, sorted_logs)
            turns.append(current_turn)

        # 关联 LLM 调用到 Turn
        self._associate_llm_calls(turns)

        # 计算延迟分解和收集 LLM 统计
        total_llm_calls = 0
        total_llm_latency = 0.0
        for turn in turns:
            self._calculate_latency_breakdown(turn)
            total_llm_calls += len(turn.llm_calls)
            total_llm_latency += sum(c.get("request_latency_ms", 0) for c in turn.llm_calls)

            # 提取 Turn 级别的 TTFT
            for event in turn.events:
                if event.event_type == EventType.TTFT_OBSERVED:
                    ttft_match = re.search(r"(\d+)ms", event.message)
                    if ttft_match:
                        turn.ttft_ms = int(ttft_match.group(1))
                        break

        # 更新 metrics
        metrics.llm_call_count = total_llm_calls
        metrics.llm_total_latency_ms = total_llm_latency
        if total_llm_calls > 0:
            metrics.llm_avg_latency_ms = total_llm_latency / total_llm_calls
        metrics.user_turns = len([t for t in turns if "user_turn" in t.turn_type])
        metrics.agent_turns = len([t for t in turns if t.ai_response])

        report.turns = turns
        report.total_turns = len(turns)
        if turns:
            report.total_duration_ms = sum(t.duration_ms for t in turns)
            report.avg_turn_duration_ms = report.total_duration_ms / len(turns)

        return report

    def _extract_user_input(self, turn: Turn, start_ts: datetime, sorted_logs: List[Tuple[datetime, str, Dict]]) -> None:
        """从日志中提取用户输入"""
        # 在 Turn 开始后的日志中查找带有 transcript 的消息
        for ts_dt, _, log in sorted_logs:
            if ts_dt < start_ts:
                continue
            message = log.get("message", "")

            # 查找 isFinal=true 的 transcript
            if "isFinal\":true" in message or "isFinal: true" in message:
                transcript, confidence = self._extract_transcript(message)
                if transcript:
                    turn.user_transcript = transcript
                    turn.user_transcript_confidence = confidence
                    return

            # 查找简单的 transcript 格式
            if "Received transcript from user" in message:
                transcript, confidence = self._extract_transcript(message)
                if transcript:
                    turn.user_transcript = transcript
                    turn.user_transcript_confidence = confidence
                    return

    def _extract_user_input_from_generating(self, turn: Turn, start_ts: datetime, sorted_logs: List[Tuple[datetime, str, Dict]]) -> None:
        """从 'Generating response for:' 日志中提取用户输入"""
        for ts_dt, _, log in sorted_logs:
            if ts_dt < start_ts:
                continue
            message = log.get("message", "")

            # 查找 "Generating response for:" 模式
            match = re.search(USER_INPUT_PATTERN, message)
            if match:
                turn.user_transcript = match.group(1).strip()
                turn.user_transcript_confidence = 1.0  # 已经被系统处理，置信度设为 1
                return

    def _finalize_turn(self, turn: Turn, sorted_logs: List[Tuple[datetime, str, Dict]]) -> None:
        """完成 Turn 的最终处理"""
        # 计算持续时间
        if turn.start_timestamp and turn.end_timestamp:
            start_ts = parse_timestamp(turn.start_timestamp)
            end_ts = parse_timestamp(turn.end_timestamp)
            if start_ts and end_ts:
                turn.duration_ms = (end_ts - start_ts).total_seconds() * 1000

        # 收集 Turn 内的事件
        self._collect_turn_events(turn, sorted_logs)

        # 基于事件和多组件日志识别当前 Turn 的异常
        self._detect_turn_anomalies(turn)

    def _collect_turn_events(self, turn: Turn, sorted_logs: List[Tuple[datetime, str, Dict]]) -> None:
        """收集 Turn 内的事件"""
        if not turn.start_timestamp or not turn.end_timestamp:
            return

        start_ts = parse_timestamp(turn.start_timestamp)
        end_ts = parse_timestamp(turn.end_timestamp)
        if not start_ts or not end_ts:
            return

        ai_phrases = []

        for ts_dt, ts_str, log in sorted_logs:
            if start_ts <= ts_dt <= end_ts:
                message = log.get("message", "")
                event_type = self._get_event_type(message)
                duration_from_start = (ts_dt - start_ts).total_seconds() * 1000

                event = TurnEvent(
                    timestamp=ts_str,
                    timestamp_dt=ts_dt,
                    component="assistant_runtime",
                    event_type=event_type,
                    message=message,
                    duration_from_turn_start_ms=duration_from_start,
                )
                turn.events.append(event)

                # 提取 AI 响应 - 收集所有 phrases
                if "Saying phrase:" in message:
                    match = re.search(r'Saying phrase: (.+)$', message)
                    if match:
                        phrase = match.group(1).strip()
                        if phrase and phrase not in ai_phrases:
                            ai_phrases.append(phrase)

                # 也从 Received end 提取
                elif "Received end:" in message:
                    ai_response = self._extract_ai_response(message)
                    if ai_response and ai_response not in ai_phrases:
                        ai_phrases.append(ai_response)

                # 提取工具调用 - Runtime 收到工具结果 (视为结束事件)
                if "toolResult" in message or "AgentCompletionResponse" in message:
                    tool_call = self._extract_tool_call(message)
                    if tool_call:
                        self._update_tool_call(
                            turn=turn,
                            tool_call=tool_call,
                            source_component="assistant_runtime",
                            phase="end",
                            ts_dt=ts_dt,
                            ts_str=ts_str,
                        )

                # 从 LLM generation finished(type=tool) 中提取工具调用 (视为开始事件)
                if "LLM generation has finished" in message and '"type":"tool"' in message:
                    tool_call = self._extract_tool_call_from_llm(message)
                    if tool_call:
                        self._update_tool_call(
                            turn=turn,
                            tool_call=tool_call,
                            source_component="assistant_runtime",
                            phase="start",
                            ts_dt=ts_dt,
                            ts_str=ts_str,
                        )

                if any(
                    kw in message
                    for kw in ("clientTool", "serverTool", "Calling client tool", "Client tool completed", "Error calling tool")
                ):
                    tool_call = self._extract_simple_tool_call(message)
                    if tool_call:
                        if "calling client tool" in message.lower() or "calling server tool" in message.lower():
                            phase = "start"
                        elif "completed" in message.lower() or "error calling tool" in message.lower():
                            phase = "end"
                        else:
                            phase = "unknown"

                        self._update_tool_call(
                            turn=turn,
                            tool_call=tool_call,
                            source_component="assistant_runtime",
                            phase=phase,
                            ts_dt=ts_dt,
                            ts_str=ts_str,
                        )

        # 合并所有 phrases
        if ai_phrases:
            turn.ai_phrases = ai_phrases
            turn.ai_response = " ".join(ai_phrases)

        # 收集跨组件的工具调用信息 (agent_service / nca / aig)
        self._collect_tool_calls_from_components(turn)

        # 收集组件时间线
        self._collect_component_timeline(turn, sorted_logs)

    def _collect_component_timeline(self, turn: Turn, sorted_logs: List[Tuple[datetime, str, Dict]]) -> None:
        """收集 Turn 内各组件的关键事件时间线（只保留关键节点）"""
        if not turn.start_timestamp or not turn.end_timestamp:
            return

        start_ts = parse_timestamp(turn.start_timestamp)
        end_ts = parse_timestamp(turn.end_timestamp)
        if not start_ts or not end_ts:
            return

        # ========== Assistant Runtime 关键事件模式 ==========
        # - 发送请求(grpc)
        # - 第一次接收到回复/收到回复结束
        # - 发起打断
        # - tool call start/end
        # - error
        ar_patterns = [
            # gRPC 请求 (严格匹配，排除普通 response)
            (r'Sending (init |generation )?request', 'grpc_send', 'AR'),
            (r'Generating response for:', 'grpc_send', 'AR'),
            # 第一次接收回复
            (r'Saying phrase:', 'first_response', 'AR'),
            # 收到回复结束
            (r'LLM generation has finished', 'response_end', 'AR'),
            (r'LLM generation and speaking has been completed', 'response_end', 'AR'),
            # 打断 (严格匹配，避免误匹配 "interruptible" / "uninterruptible")
            (r'Interrupt(ing|ed) the generation', 'interruption', 'AR'),
            (r'User interrupt', 'interruption', 'AR'),
            # Tool call start
            (r'"type"\s*:\s*"tool"', 'tool_call_start', 'AR'),
            (r'Calling (client |server )?tool', 'tool_call_start', 'AR'),
            (r'(clientTool|serverTool)\s*[:=]', 'tool_call_start', 'AR'),
            # Tool call end
            (r'Received toolResult', 'tool_call_end', 'AR'),
            (r'(Client |Server )?[Tt]ool completed', 'tool_call_end', 'AR'),
        ]

        # ========== NCA 关键事件模式 ==========
        # - tool call start/end
        # - llm request start/end
        # - 生成回复(start/end)
        # - error
        nca_patterns = [
            # Tool call
            (r'(Calling|calling).*(tool|Tool)', 'tool_call_start', 'nca'),
            (r'(clientTool|serverTool)', 'tool_call_start', 'nca'),
            (r'(tool|Tool).*(completed|finished|result|response)', 'tool_call_end', 'nca'),
            # LLM request
            (r'\[GMG Client\]\[.+\]', 'llm_request_start', 'nca'),
            (r'(request|send)\s+model', 'llm_request_start', 'nca'),
            (r'(LLM|llm).*(response|complete|finish|end)', 'llm_request_end', 'nca'),
            # 生成回复
            (r'(Generat|generat).*(start|begin)', 'generation_start', 'nca'),
            (r'(Start|start).*(generat|response)', 'generation_start', 'nca'),
            (r'(Generat|generat).*(end|complete|finish)', 'generation_end', 'nca'),
            (r'(response|generation).*(complete|finish|end)', 'generation_end', 'nca'),
            # Error
            (r'(ERROR|Error|error)', 'error', 'nca'),
        ]

        # ========== AIG 关键事件模式 ==========
        # - tool call start/end
        # - 调用agent-service start/end
        # - error
        aig_patterns = [
            # Tool call
            (r'(Calling|calling).*(tool|Tool)', 'tool_call_start', 'aig'),
            (r'(tool|Tool).*(completed|finished|result|response)', 'tool_call_end', 'aig'),
            # Agent service call
            (r'(Calling|calling|request).*(agent|Agent)', 'agent_service_call_start', 'aig'),
            (r'(agent|Agent).*(response|complete|finish)', 'agent_service_call_end', 'aig'),
            # Error
            (r'(ERROR|Error|error)', 'error', 'aig'),
        ]

        # ========== GMG 关键事件模式 ==========
        # - llm request start/end
        # - 生成回复(start/end)
        # - error
        gmg_patterns = [
            # LLM request
            (r'(Request|request).*(start|begin|received)', 'llm_request_start', 'gmg'),
            (r'(Sending|sending|forward).*(request|LLM|model)', 'llm_request_start', 'gmg'),
            (r'Request completed', 'llm_request_end', 'gmg'),
            (r'(Request|request).*(complete|finish|end)', 'llm_request_end', 'gmg'),
            (r'request_latency', 'llm_request_end', 'gmg'),
            # 生成回复
            (r'(Generat|generat).*(start|begin)', 'generation_start', 'gmg'),
            (r'(first|First).*(token|chunk)', 'generation_start', 'gmg'),
            (r'(Generat|generat).*(end|complete|finish)', 'generation_end', 'gmg'),
            (r'(Stream|stream).*(end|complete|finish)', 'generation_end', 'gmg'),
            # Error
            (r'(ERROR|Error|error)', 'error', 'gmg'),
        ]

        # ========== Agent Service 关键事件模式 ==========
        # - tool call start/end
        # - error
        agent_service_patterns = [
            # Tool call
            (r'(Calling|calling).*(tool|Tool)', 'tool_call_start', 'agent_service'),
            (r'(clientTool|serverTool)', 'tool_call_start', 'agent_service'),
            (r'(tool|Tool).*(completed|finished|result|response)', 'tool_call_end', 'agent_service'),
            # Error
            (r'(ERROR|Error|error)', 'error', 'agent_service'),
        ]

        timeline: List[Dict[str, Any]] = []

        # ---------- 1) Assistant Runtime 关键事件 ----------
        for ts_dt, ts_str, log in sorted_logs:
            if not (start_ts <= ts_dt <= end_ts):
                continue

            message = log.get("message", "")
            level = log.get("level", "").upper()
            duration_from_start = (ts_dt - start_ts).total_seconds() * 1000

            # 优先检查 log level 是否为 error/warn
            if level in ("ERROR", "FATAL"):
                timeline.append({
                    "timestamp": ts_str,
                    "offset_ms": round(duration_from_start, 1),
                    "component": "AR",
                    "event": "error",
                    "detail": message[:100],
                })
                continue

            for pattern, event_name, component in ar_patterns:
                if re.search(pattern, message):
                    # 避免把普通 log 中的 "error" 字眼误判为 error 事件
                    if event_name in ("error", "warning") and level not in ("ERROR", "WARN", "WARNING"):
                        continue
                    timeline.append({
                        "timestamp": ts_str,
                        "offset_ms": round(duration_from_start, 1),
                        "component": component,
                        "event": event_name,
                        "detail": message[:100],
                    })
                    break  # 每条日志只匹配一个事件

        # ---------- 2) 其他组件关键事件 ----------
        component_pattern_map = {
            "nca": nca_patterns,
            "aig": aig_patterns,
            "gmg": gmg_patterns,
            "agent_service": agent_service_patterns,
        }

        for comp_name, patterns in component_pattern_map.items():
            comp_logs = self.logs.get(comp_name, [])
            for log in comp_logs:
                ts_str = log.get("@timestamp", "")
                ts_dt = parse_timestamp(ts_str)
                if not ts_dt or not (start_ts <= ts_dt <= end_ts):
                    continue

                message = log.get("message", "") or ""
                level = log.get("level", "").upper()
                duration_from_start = (ts_dt - start_ts).total_seconds() * 1000

                # 优先检查 log level 是否为 error
                if level in ("ERROR", "FATAL"):
                    timeline.append({
                        "timestamp": ts_str,
                        "offset_ms": round(duration_from_start, 1),
                        "component": comp_name,
                        "event": "error",
                        "detail": message[:100],
                    })
                    continue

                for pattern, event_name, _ in patterns:
                    match = re.search(pattern, message)
                    if match:
                        # 避免把普通 log 中的 "error" 字眼误判为 error 事件
                        if event_name == "error" and level not in ("ERROR", "FATAL"):
                            continue
                        
                        extra_detail = ""
                        # 针对特定事件尝试从 message 中提取更多信息 (如 model name)
                        if "llm" in event_name or "generation" in event_name:
                             # 适配 [GMG Client][request-type] 格式
                             # Example: [GMG Client][filler-phrase] Chat completion streaming call
                             client_match = re.search(r'\[GMG Client\]\[([\w-]+)\]', message)
                             if client_match:
                                 # FOUND: This is a high-confidence match for the specific agent type.
                                 # We use this as the primary extra detail.
                                 extra_detail = f" [{client_match.group(1)}]"
                             elif comp_name == 'gmg':
                                 # GMG Specific extraction from log fields
                                 app_name = log.get('ai_app_name')
                                 model = log.get('model')
                                 
                                 details = []
                                 if app_name:
                                     details.append(app_name)
                                 if model:
                                     details.append(model)
                                 
                                 if details:
                                     extra_detail = f" [{', '.join(details)}]"
                             else:
                                 # Fallback extraction logic
                                 model_match = re.search(r'(model|ai_app_name)\s*[:=]\s*"?([\w.-]+)"?', message)
                                 if model_match:
                                     extra_detail = f" [{model_match.group(2)}]"
                                 else:
                                     type_match = re.search(r'(type|class)\s*[:=]\s*"?(\w+)"?', message, re.IGNORECASE)
                                     if type_match:
                                         extra_detail = f" [{type_match.group(2)}]"
                        
                        # Only use general regex groups if specific extraction failed and we still want detail
                        if not extra_detail and match.groups():
                            captured = [g for g in match.groups() if g]
                            if captured:
                                extra_detail = f" ({', '.join(captured)})"

                        # Generate pairing_key for precise start/end matching
                        pairing_key = self._normalize_pairing_key(event_name, extra_detail)

                        timeline.append({
                            "timestamp": ts_str,
                            "offset_ms": round(duration_from_start, 1),
                            "component": comp_name,
                            "event": event_name,
                            "detail": message[:100] + extra_detail,
                            "pairing_key": pairing_key,
                            # 同时保存结构化 extra info 供前端使用
                            "meta": {
                                "extra_detail": extra_detail.strip()
                            }
                        })
                        break  # 每条日志只匹配一个事件

        # ---------- 3) 添加已提取的 LLM 调用信息 ----------
        for llm_call in turn.llm_calls:
            llm_ts_str = llm_call.get("timestamp", "")
            llm_ts = parse_timestamp(llm_ts_str)
            offset = 0.0
            if llm_ts and start_ts:
                offset = (llm_ts - start_ts).total_seconds() * 1000
            timeline.append({
                "timestamp": llm_ts_str,
                "offset_ms": round(offset, 1),
                "component": "GMG",
                "event": "llm_call",
                "detail": f"{llm_call.get('ai_app_name', 'LLM')}: {llm_call.get('request_latency_ms', 0)}ms",
            })

        # ---------- 4) 添加已提取的 Tool Call 信息 ----------
        for tc in turn.tool_calls:
            # Tool call start
            tc_start_ts_str = tc.get("start_timestamp")
            if tc_start_ts_str:
                tc_start_ts = parse_timestamp(tc_start_ts_str)
                offset = 0.0
                if tc_start_ts and start_ts:
                    offset = (tc_start_ts - start_ts).total_seconds() * 1000
                timeline.append({
                    "timestamp": tc_start_ts_str,
                    "offset_ms": round(offset, 1),
                    "component": tc.get("source_component", "AR"),
                    "event": "tool_call_start",
                    "detail": f"{tc.get('tool_name', 'unknown')}",
                })
            # Tool call end
            tc_end_ts_str = tc.get("end_timestamp")
            if tc_end_ts_str:
                tc_end_ts = parse_timestamp(tc_end_ts_str)
                offset = 0.0
                if tc_end_ts and start_ts:
                    offset = (tc_end_ts - start_ts).total_seconds() * 1000
                duration = tc.get("duration_ms")
                dur_str = f" ({duration:.0f}ms)" if duration is not None else ""
                timeline.append({
                    "timestamp": tc_end_ts_str,
                    "offset_ms": round(offset, 1),
                    "component": tc.get("source_component", "AR"),
                    "event": "tool_call_end",
                    "detail": f"{tc.get('tool_name', 'unknown')}{dur_str} -> {tc.get('status', 'unknown')}",
                })

        # 按时间排序并去重
        timeline.sort(key=lambda x: x.get("timestamp", ""))
        # 去重：相同 timestamp + component + event 只保留一条
        seen: Set[str] = set()
        deduped: List[Dict[str, Any]] = []
        for ev in timeline:
            key = f"{ev.get('timestamp')}|{ev.get('component')}|{ev.get('event')}"
            if key not in seen:
                seen.add(key)
                deduped.append(ev)
        turn.component_timeline = deduped

    def _collect_tool_calls_from_components(self, turn: Turn) -> None:
        """Collect tool calls for this turn from other components (agent_service / nca / aig)."""
        if not turn.start_timestamp or not turn.end_timestamp:
            return

        start_ts = parse_timestamp(turn.start_timestamp)
        end_ts = parse_timestamp(turn.end_timestamp)
        if not start_ts or not end_ts:
            return

        for comp_name in ["agent_service", "nca", "aig"]:
            comp_logs = self.logs.get(comp_name, [])
            if not comp_logs:
                continue

            for log in comp_logs:
                ts_str = log.get("@timestamp", "")
                ts_dt = parse_timestamp(ts_str)
                if not ts_dt or not (start_ts <= ts_dt <= end_ts):
                    continue

                message = (log.get("message", "") or "")
                lower = message.lower()

                tool_call: Optional[Dict[str, Any]] = None
                phase: str = "unknown"

                # 1) JSON payloads (toolResult / AgentCompletionResponse) -> 视为结束事件
                if "toolResult" in message or "AgentCompletionResponse" in message:
                    tool_call = self._extract_tool_call(message)
                    phase = "end"

                # 2) LLM-style tool metadata -> 更偏向于“开始”阶段
                if not tool_call and ('"type":"tool"' in message or '"tool":{' in message):
                    tool_call = self._extract_tool_call_from_llm(message)
                    phase = "start"

                # 3) 简单的 clientTool/serverTool 文本日志
                if not tool_call and any(
                    kw in message
                    for kw in ("clientTool", "serverTool", "Calling client tool", "Client tool completed", "Error calling tool")
                ):
                    tool_call = self._extract_simple_tool_call(message)

                    # 基于文案粗略区分开始/结束
                    if "calling client tool" in lower or "calling tool" in lower:
                        phase = "start"
                    elif "client tool completed" in lower or "tool completed" in lower or "error calling tool" in lower:
                        phase = "end"
                    else:
                        phase = "unknown"

                if not tool_call and any(
                    kw in message
                    for kw in ("[Trace][Tool] Started", "callTool starting", "callTool completed")
                ):
                    tool_call = self._extract_trace_tool_call(message)
                    if "[Trace][Tool] Started" in message or "callTool starting" in message:
                        phase = "start"
                    elif "callTool completed" in message:
                        phase = "end"
                    else:
                        phase = "unknown"

                if tool_call:
                    self._update_tool_call(
                        turn=turn,
                        tool_call=tool_call,
                        source_component=comp_name,
                        phase=phase,
                        ts_dt=ts_dt,
                        ts_str=ts_str,
                    )

    def _detect_turn_anomalies(self, turn: Turn) -> None:
        """识别单个 Turn 中的异常情况

        目前包含几类:
        - missing_ai_response: 有用户输入但没有任何 AI 回复
        - slow_ttft: TTFT 过高
        - assistant_runtime_error / warning: Turn 内 assistant_runtime 出现错误/告警
        - <component>_error / <component>_warning: nca/aig/gmg/agent_service 中的错误/告警
        - interrupted_without_completion: 被打断且没有看到完整 "LLM generation and speaking has been completed"
        """

        anomalies: List[Dict[str, Any]] = []

        # 1) 有用户输入但没有 AI 回复
        if turn.user_transcript and not turn.ai_response:
            anomalies.append({
                "type": "missing_ai_response",
                "severity": "error",
                "message": "User transcript exists but no AI response was generated in this turn.",
            })

        # 2) TTFT 过高
        if turn.ttft_ms is not None and turn.ttft_ms > 2000:
            anomalies.append({
                "type": "slow_ttft",
                "severity": "warning",
                "message": f"TTFT is {turn.ttft_ms} ms (> 2000 ms).",
            })

        # 3) assistant_runtime 内的错误/告警
        ar_errors: List[str] = []
        ar_warnings: List[str] = []
        for ev in turn.events:
            if ev.event_type == EventType.ERROR:
                ar_errors.append(ev.message)
            elif ev.event_type == EventType.WARNING:
                ar_warnings.append(ev.message)

        if ar_errors:
            anomalies.append({
                "type": "assistant_runtime_error",
                "severity": "error",
                "message": f"{len(ar_errors)} error log(s) in assistant_runtime during this turn. Example: {ar_errors[0][:100]}",
            })

        if ar_warnings:
            anomalies.append({
                "type": "assistant_runtime_warning",
                "severity": "warning",
                "message": f"{len(ar_warnings)} warning log(s) in assistant_runtime during this turn. Example: {ar_warnings[0][:100]}",
            })

        # 4) 其他组件 (agent_service, nca, aig, gmg) 中的错误/告警
        if turn.start_timestamp and turn.end_timestamp:
            start_ts = parse_timestamp(turn.start_timestamp)
            end_ts = parse_timestamp(turn.end_timestamp)
            if start_ts and end_ts:
                for comp_name in ["agent_service", "nca", "aig", "gmg"]:
                    comp_logs = self.logs.get(comp_name, [])
                    comp_errors: List[str] = []
                    comp_warnings: List[str] = []

                    for log in comp_logs:
                        ts_str = log.get("@timestamp", "")
                        ts_dt = parse_timestamp(ts_str)
                        if not ts_dt or not (start_ts <= ts_dt <= end_ts):
                            continue

                        msg = (log.get("message", "") or "")
                        if re.search(r"error|failed|failure|fatal", msg, re.IGNORECASE):
                            comp_errors.append(msg)
                        elif re.search(r"warn|timeout|DEADLINE_EXCEEDED", msg, re.IGNORECASE):
                            comp_warnings.append(msg)

                    if comp_errors:
                        anomalies.append({
                            "type": f"{comp_name}_error",
                            "severity": "error",
                            "message": f"{comp_name} has {len(comp_errors)} error log(s) in this turn. Example: {comp_errors[0][:100]}",
                        })

                    if comp_warnings:
                        anomalies.append({
                            "type": f"{comp_name}_warning",
                            "severity": "warning",
                            "message": f"{comp_name} has {len(comp_warnings)} warning/timeout log(s) in this turn. Example: {comp_warnings[0][:100]}",
                        })

        # 5) 被打断但没有看到完整的 Turn 完成日志
        has_turn_complete = any(ev.event_type == EventType.TURN_COMPLETE for ev in turn.events)
        if turn.was_interrupted and not has_turn_complete:
            anomalies.append({
                "type": "interrupted_without_completion",
                "severity": "warning",
                "message": "Turn was interrupted and no 'LLM generation and speaking has been completed' event was observed.",
            })

        turn.anomalies = anomalies

    def _update_tool_call(
        self,
        turn: Turn,
        tool_call: Dict[str, Any],
        *,
        source_component: str,
        phase: str,
        ts_dt: datetime,
        ts_str: str,
    ) -> None:
        """将一次工具调用的信息合并到 Turn 中, 补充开始/结束时间和持续时长。

        - phase: "start" / "end" / "unknown" 表示当前日志在工具调用生命周期中的位置
        """
        tool_name = tool_call.get("tool_name") or ""
        tool_call_id = tool_call.get("tool_call_id") or ""
        tool_type = self._normalize_tool_type(tool_call.get("tool_type"))
        status = self._normalize_tool_status(tool_call.get("status", "unknown"))
        input_payload = tool_call.get("input", "")
        output_payload = tool_call.get("output", "")

        # 查找是否已有同一个工具调用
        existing: Optional[Dict[str, Any]] = None
        for tc in turn.tool_calls:
            if (
                tc.get("tool_call_id") == tool_call_id
                and tc.get("tool_name") == tool_name
                and tc.get("source_component") == source_component
            ):
                existing = tc
                break

        if existing is None:
            existing = {
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "tool_type": tool_type,
                "source_component": source_component,
                "start_timestamp": None,
                "end_timestamp": None,
                "duration_ms": None,
                "status": status,
                "input": input_payload,
                "output": output_payload,
            }
            turn.tool_calls.append(existing)
        else:
            # 补充输入/输出, 避免覆盖已经存在的更完整信息
            if input_payload and not existing.get("input"):
                existing["input"] = input_payload
            if output_payload and not existing.get("output"):
                existing["output"] = output_payload
            if existing.get("tool_type") in (None, "", "unknown") and tool_type != "unknown":
                existing["tool_type"] = tool_type

            # 如果之前不是 failed, 则可以被更新为 failed / success 等更准确状态
            if existing.get("status") != "failed":
                existing["status"] = status or existing.get("status", "unknown")

        # 更新时间信息
        if phase == "start":
            if not existing.get("start_timestamp"):
                existing["start_timestamp"] = ts_str
        elif phase == "end":
            existing["end_timestamp"] = ts_str
        else:  # unknown
            if not existing.get("start_timestamp") and not existing.get("end_timestamp"):
                existing["start_timestamp"] = ts_str
                existing["end_timestamp"] = ts_str
            elif not existing.get("end_timestamp"):
                existing["end_timestamp"] = ts_str

        # 为向后兼容保留一个通用的 source_timestamp
        existing["source_timestamp"] = ts_str

        # 计算持续时长, 确保 start <= end
        start_ts_str = existing.get("start_timestamp")
        end_ts_str = existing.get("end_timestamp")
        if start_ts_str and end_ts_str:
            start_ts = parse_timestamp(start_ts_str)
            end_ts = parse_timestamp(end_ts_str)
            if start_ts and end_ts:
                # 日志顺序可能导致我们先看到“结束”再看到“开始”, 这里做一次纠正
                if start_ts > end_ts:
                    start_ts, end_ts = end_ts, start_ts
                    start_ts_str, end_ts_str = end_ts_str, start_ts_str
                    existing["start_timestamp"] = start_ts_str
                    existing["end_timestamp"] = end_ts_str

                existing["duration_ms"] = (end_ts - start_ts).total_seconds() * 1000.0

    def _extract_tool_call(self, message: str) -> Optional[Dict[str, Any]]:
        """从日志消息中提取工具调用"""
        # 匹配 Received toolResult 格式
        match = re.search(r'Received toolResult\s*(\{.+\})', message)
        if match:
            try:
                tool_data = json.loads(match.group(1))
                return {
                    "tool_name": tool_data.get("name", ""),
                    "tool_call_id": tool_data.get("toolCallId", ""),
                    "tool_type": self._normalize_tool_type(tool_data.get("type")),
                    "status": self._normalize_tool_status(tool_data.get("status")),
                    "input": tool_data.get("input", ""),
                    "output": tool_data.get("output", "")[:200] + "..." if len(tool_data.get("output", "")) > 200 else tool_data.get("output", ""),
                    "timestamp": tool_data.get("timestamp"),
                }
            except json.JSONDecodeError:
                pass

        # 匹配 AgentCompletionResponse toolResult 格式
        if "AgentCompletionResponse" in message and '"toolResult"' in message:
            match = re.search(r'AgentCompletionResponse:\s*(\{.+\})', message)
            if match:
                try:
                    data = json.loads(match.group(1))
                    tool_result = data.get("payload", {}).get("toolResult", {})
                    if tool_result:
                        output = tool_result.get("output", "")
                        return {
                            "tool_name": tool_result.get("name", ""),
                            "tool_call_id": tool_result.get("toolCallId", ""),
                            "tool_type": self._normalize_tool_type(tool_result.get("type")),
                            "status": self._normalize_tool_status(tool_result.get("status")),
                            "input": tool_result.get("input", ""),
                            "output": output[:200] + "..." if len(output) > 200 else output,
                            "timestamp": tool_result.get("timestamp"),
                        }
                except json.JSONDecodeError:
                    pass

        match = re.search(
            r'toolAction":\{"toolName":"([^"]+)","input":"([^"]*)","output":"([^"]*)","status":([^,}]+)',
            message,
        )
        if match:
            return {
                "tool_name": match.group(1),
                "tool_call_id": "",
                "tool_type": "unknown",
                "status": self._normalize_tool_status(match.group(4)),
                "input": match.group(2),
                "output": match.group(3)[:200] + "..." if len(match.group(3)) > 200 else match.group(3),
                "timestamp": None,
            }
        return None

    def _extract_tool_call_from_llm(self, message: str) -> Optional[Dict[str, Any]]:
        """从 LLM generation finished 消息中提取工具调用"""
        # 匹配 "tool" 类型的消息
        match = re.search(r'"tool":\{"id":"([^"]+)","name":"([^"]+)"', message)
        if match:
            tool_call_id = match.group(1)
            tool_name = match.group(2)

            # 提取 tool 自身的 status，而不是外层 LLM 事件的 finished status
            status_match = re.search(r'"tool":\{.*?"status":"([^"]+)"', message)
            status = self._normalize_tool_status(status_match.group(1) if status_match else None)
            tool_type_match = re.search(
                r'"(?:toolType|type|oneofKind)":"(clientTool|serverTool|client|server)"',
                message,
                re.IGNORECASE,
            )

            return {
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "tool_type": self._normalize_tool_type(tool_type_match.group(1) if tool_type_match else None),
                "status": status,
            }
        return None

    def _extract_trace_tool_call(self, message: str) -> Optional[Dict[str, Any]]:
        """Extract tool lifecycle events from NCA-style trace logs."""
        match = re.search(
            r"\[Trace\]\[Tool\] Started: toolName=([^,]+), toolType=([^,]+), callId=([^\s,]+)",
            message,
        )
        if match:
            return {
                "tool_name": match.group(1),
                "tool_call_id": match.group(3),
                "tool_type": self._normalize_tool_type(match.group(2)),
                "status": "unknown",
                "input": "",
                "output": "",
                "timestamp": None,
            }

        match = re.search(r"\[Tool\]\[([^\]]+)\]\[([^\]]+)\] callTool starting", message)
        if match:
            return {
                "tool_name": match.group(1),
                "tool_call_id": "",
                "tool_type": self._normalize_tool_type(match.group(2)),
                "status": "unknown",
                "input": "",
                "output": "",
                "timestamp": None,
            }

        match = re.search(r"\[Tool\]\[([^\]]+)\] callTool completed, success:\s*(true|false)", message, re.IGNORECASE)
        if match:
            return {
                "tool_name": match.group(1),
                "tool_call_id": "",
                "tool_type": "unknown",
                "status": self._normalize_tool_status(match.group(2)),
                "input": "",
                "output": "",
                "timestamp": None,
            }

        return None

    def _extract_simple_tool_call(self, message: str) -> Optional[Dict[str, Any]]:
        """从简单的 clientTool/serverTool 文本日志中尽力提取工具调用信息。"""
        lower = message.lower()

        status = "unknown"
        if "error calling tool" in lower or "failed" in lower or "error" in lower:
            status = "failed"
        elif "completed" in lower or "tool completed" in lower or "success" in lower:
            status = "success"

        tool_name = ""
        tool_type = "unknown"

        # 尝试从 clientTool:/serverTool: 中解析工具名
        m = re.search(r"(clientTool|serverTool)[:=]\s*([\w.-]+)", message)
        if m:
            tool_type = self._normalize_tool_type(m.group(1))
            tool_name = m.group(2)
        else:
            m = re.search(r"Calling\s+(client|server)\s+tool[:\s]*\"?([\w.-]+)\"?", message, re.IGNORECASE)
            if m:
                tool_type = self._normalize_tool_type(m.group(1))
                tool_name = m.group(2)

        if not tool_name:
            # 或者更通用的 tool=xxx / tool: xxx
            m = re.search(r"tool\s*[:=]\s*\"?([\w.-]+)\"?", message)
            if m:
                tool_name = m.group(1)

        if not tool_name:
            m = re.search(r"Received\s+(clientTool|serverTool),\s*name:\s*([\w.-]+)", message)
            if m:
                tool_type = self._normalize_tool_type(m.group(1))
                tool_name = m.group(2)

        if not tool_name and status == "unknown":
            # 名字和状态都推不出来，说明信息太少，直接忽略这条日志
            return None

        return {
            "tool_name": tool_name or "(unknown)",
            "tool_call_id": "",
            "tool_type": tool_type,
            "status": status,
            "input": "",
            "output": "",
            "timestamp": None,
        }

    def _associate_llm_calls(self, turns: List[Turn]) -> None:
        """关联 LLM 调用到对应的 Turn

        使用精确的时间窗口，避免 LLM 调用被重复关联到多个 Turn
        """
        gmg_logs = self.logs.get("gmg", [])

        # 收集 LLM 调用并按时间排序
        llm_calls = []
        for log in gmg_logs:
            if log.get("request_latency"):
                ts_str = log.get("@timestamp", "")
                ts = parse_timestamp(ts_str)
                if ts:
                    llm_calls.append({
                        "timestamp": ts_str,
                        "timestamp_dt": ts,
                        "ai_app_name": log.get("ai_app_name", ""),
                        "model": log.get("model", ""),
                        "request_latency_ms": log.get("request_latency", 0),
                        "llm_processing_ms": log.get("llm_processing_ms", 0),
                        "llm_1st_chunk_ms": log.get("llm_1st_chunk_ms", 0),
                        "total_tokens": log.get("total_tokens", 0),
                        "total_cost": log.get("total_cost", 0.0),
                        "assigned": False,  # 标记是否已分配
                    })

        # 按时间排序
        llm_calls.sort(key=lambda x: x["timestamp_dt"])

        # 关联到 Turn - 使用精确的时间窗口
        for turn in turns:
            if not turn.start_timestamp or not turn.end_timestamp:
                continue
            start_ts = parse_timestamp(turn.start_timestamp)
            end_ts = parse_timestamp(turn.end_timestamp)
            if not start_ts or not end_ts:
                continue

            # 使用更精确的时间窗口:
            # - 向前 0.5 秒 (LLM 调用可能在 Turn 开始前一点点发起)
            # - 向后 1 秒 (LLM 调用可能在 Turn 结束后一点点完成)
            window_start = start_ts - timedelta(milliseconds=500)
            window_end = end_ts + timedelta(seconds=1)

            for call in llm_calls:
                # 跳过已分配的调用
                if call["assigned"]:
                    continue

                call_ts = call["timestamp_dt"]
                if window_start <= call_ts <= window_end:
                    call["assigned"] = True
                    turn.llm_calls.append({
                        k: v for k, v in call.items() if k not in ("timestamp_dt", "assigned")
                    })

    def _calculate_latency_breakdown(self, turn: Turn) -> None:
        """计算 Turn 的延迟分解"""
        if not turn.events:
            return

        breakdown = {}

        # 计算 LLM 总延迟
        if turn.llm_calls:
            breakdown["llm_total_ms"] = sum(c.get("request_latency_ms", 0) for c in turn.llm_calls)
            breakdown["llm_count"] = len(turn.llm_calls)

        # 计算其他延迟
        breakdown["total_ms"] = turn.duration_ms
        if "llm_total_ms" in breakdown:
            breakdown["non_llm_ms"] = turn.duration_ms - breakdown["llm_total_ms"]

        turn.latency_breakdown = breakdown


# ============================================================================
# Main Entry Point
# ============================================================================


def main(argv: list[str] | None = None) -> int:
    """Turn 分析主入口"""
    parser = argparse.ArgumentParser(
        description="IVA Voice Call Analyzer - 语音通话分析",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python turn_analyzer.py ./output/iva_session/s-xxx-yyy
  python turn_analyzer.py ./output/iva_session/s-xxx-yyy --format markdown
  python turn_analyzer.py ./output/iva_session/s-xxx-yyy -o turn_report.json
  python turn_analyzer.py ./output/iva_session/s-xxx-yyy --viz
  python turn_analyzer.py ./output/iva_session/s-xxx-yyy --html
        """
    )
    parser.add_argument("session_dir", help="Session output directory")
    parser.add_argument("--format", "-f", choices=["table", "markdown", "json"],
                        default="table", help="Output format (default: table)")
    parser.add_argument("--output", "-o", help="Output file")
    parser.add_argument("--viz", "-v", action="store_true",
                        help="Generate Mermaid visualization files")
    parser.add_argument("--html", action="store_true",
                        help="Generate HTML visualization report")

    args = parser.parse_args(argv)

    session_dir = Path(args.session_dir)
    if not session_dir.exists():
        print(f"❌ Directory not found: {session_dir}", file=sys.stderr)
        return 1

    try:
        analyzer = VoiceCallAnalyzer(session_dir)
        report = analyzer.analyze()

        if args.format == "json":
            output = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
        elif args.format == "markdown":
            output = format_report_markdown(report)
        else:
            output = format_report_table(report)

        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"✅ Report saved to: {output_path}")
        else:
            print(output)

        # 生成可视化
        if args.viz:
            viz_files = generate_visualizations(report, session_dir)
            print("\n📊 Visualizations generated:")
            for name, path in viz_files.items():
                print(f"   - {name}: {path}")

        # 生成 HTML 报告
        if args.html:
            html_path = session_dir / "turn_report.html"
            generate_html_report(report, html_path)
            print(f"\n🌐 HTML Report: {html_path}")

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
