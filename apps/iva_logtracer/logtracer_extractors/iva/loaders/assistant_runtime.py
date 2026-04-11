#!/usr/bin/env python3
"""
IVA AssistantRuntimeLoader - Assistant Runtime 日志加载器

特点:
- 无依赖，是追踪链的起点
- 支持 session_id 或 conversation_id 查询
- post_load 提取 conversation_id, srs_session_id, sgs_session_id
"""

import re
from typing import TYPE_CHECKING

try:
    from ...loaders import LogLoader
except ImportError:
    from loaders import LogLoader

if TYPE_CHECKING:
    try:
        from ..trace_context import TraceContext
    except ImportError:
        from trace_context import TraceContext


class AssistantRuntimeLoader(LogLoader):
    """
    Assistant Runtime 日志加载器

    这是追踪链的起点，可以从 session_id、conversation_id 或 account_id 开始
    加载后会提取 conversation_id 和 srs/sgs_session_id 供其他 loader 使用

    使用 account_id 查询时，会返回该账户的最近日志，通常用于：
    - 电话被转接但没有 conversationId 的情况
    - 不知道 sessionId 时查看账户的最近活动
    """

    META_SOURCE_INCLUDES = [
        "@timestamp",
        "sessionId",
        "conversationId",
        "accountId",
        "message",
    ]

    @property
    def name(self) -> str:
        return "assistant_runtime"

    @property
    def index_pattern(self) -> str:
        return "*:*-logs-air_assistant_runtime-*"

    @property
    def depends_on_any(self) -> list:
        """需要 session_id、conversation_id、account_id 或 extension_id 其中之一"""
        return ["session_id", "conversation_id", "account_id", "extension_id"]

    def build_query(self, ctx: "TraceContext") -> str:
        """优先使用 session_id 查询，否则使用 conversation_id，最后使用 account_id"""
        if ctx.session_id:
            return f'sessionId:"{ctx.session_id}"'
        if ctx.conversation_id:
            return f'conversationId:"{ctx.conversation_id}"'
        return f'accountId:"{ctx.account_id}"'

    def get_meta_source_includes(self) -> list[str]:
        """最小字段集合，用于并发前的隐藏 prefetch。"""
        return list(self.META_SOURCE_INCLUDES)

    def extract_context_from_logs(self, ctx: "TraceContext", logs: list) -> None:
        """从 assistant_runtime 日志提取后续 loader 依赖的关联 ID。"""
        if not logs:
            return

        # 提取 conversation_id
        if not ctx.conversation_id:
            for log in logs:
                conv_id = log.get("conversationId")
                if conv_id:
                    ctx.conversation_id = conv_id
                    print(f"   ✅ Found conversationId: {conv_id}")
                    break

        # 提取 session_id
        if not ctx.session_id:
            for log in logs:
                sess_id = log.get("sessionId")
                if sess_id:
                    ctx.session_id = sess_id
                    print(f"   ✅ Found sessionId: {sess_id}")
                    break

        # 提取 account_id
        if not ctx.account_id:
            for log in logs:
                acct_id = log.get("accountId")
                if acct_id:
                    ctx.account_id = acct_id
                    print(f"   ✅ Found accountId: {acct_id}")
                    break

        # 提取 srs_session_id 和 sgs_session_id
        self._extract_srs_session_ids(ctx, logs)

    def post_load(self, ctx: "TraceContext") -> None:
        """从日志中提取派生数据"""
        logs = ctx.logs.get(self.name, [])
        self.extract_context_from_logs(ctx, logs)
    
    def _extract_srs_session_ids(self, ctx: "TraceContext", logs: list) -> None:
        """
        从日志 message 中提取 srsSessionId 和 sgsSessionId

        日志格式说明：
        - SRS (Speech Recognition Service, 语音识别):
          - 旧格式: "Speech recognition started" / "Starting speech recognition"
          - 新格式: "TTS srsOffer:" (TTS 组件使用 SRS 服务进行语音识别)
        - SGS (Speech Generation Service, 语音合成):
          - 旧格式: "Speech generation started"
          - 新格式: "STT sgsOffer:" (STT 组件使用 SGS 服务进行语音合成)

        注意：日志字段名 srsSessionId 在两种服务中都使用，但含义不同
        """
        srs_pattern = re.compile(r'"srsSessionId"\s*:\s*"([^"]+)"')

        for log in logs:
            message = log.get("message", "")

            # 提取 SRS session ID (语音识别 - Speech Recognition)
            # 旧格式: "Speech recognition started" 或 "Starting speech recognition"
            # 新格式: "TTS srsOffer:" (TTS 使用 SRS 进行识别)
            if not ctx.srs_session_id:
                if ("Speech recognition started" in message or
                    "Starting speech recognition" in message or
                    "TTS srsOffer:" in message):
                    match = srs_pattern.search(message)
                    if match:
                        ctx.srs_session_id = match.group(1)
                        print(f"   ✅ Found SRS sessionId: {ctx.srs_session_id}")

            # 提取 SGS session ID (语音合成 - Speech Generation)
            # 旧格式: "Speech generation started"
            # 新格式: "STT sgsOffer:" (STT 使用 SGS 进行合成)
            if not ctx.sgs_session_id:
                if ("Speech generation started" in message or
                    "STT sgsOffer:" in message):
                    match = srs_pattern.search(message)
                    if match:
                        ctx.sgs_session_id = match.group(1)
                        print(f"   ✅ Found SGS sessionId: {ctx.sgs_session_id}")

            if ctx.srs_session_id and ctx.sgs_session_id:
                break
