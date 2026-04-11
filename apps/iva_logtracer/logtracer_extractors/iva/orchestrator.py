#!/usr/bin/env python3
"""
IVA SessionTraceOrchestrator - IVA 会话追踪编排器

按依赖顺序执行 LogLoaders，自动处理依赖关系
支持并发加载以提高速度
"""

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Set, Type

try:
    from ..kibana_client import KibanaClient
    from ..kibana_client import parse_time_range
    from ..loaders import LogLoader
    from .loaders import ALL_LOADERS
    from .loaders.assistant_runtime import AssistantRuntimeLoader
    from .trace_context import TraceContext
except ImportError:
    from kibana_client import KibanaClient, parse_time_range
    from loaders import ALL_LOADERS, LogLoader
    from loaders.assistant_runtime import AssistantRuntimeLoader
    from trace_context import TraceContext


class SessionTraceOrchestrator:
    """
    IVA 会话追踪编排器

    负责:
    1. 管理所有 LogLoader 实例
    2. 按依赖顺序执行 loaders (同一轮内并发)
    3. 处理加载后的派生数据提取
    """

    ASSISTANT_RUNTIME_PREFETCH_SIZE = 500
    ASSISTANT_RUNTIME_ID_DEPENDENT_LOADERS = {
        "agent_service": "conversation_id",
        "nca": "conversation_id",
        "cprc_srs": "srs_session_id",
        "cprc_sgs": "sgs_session_id",
    }

    def __init__(
        self,
        client: KibanaClient,
        loader_classes: Optional[List[Type[LogLoader]]] = None,
        max_workers: int = 5,
    ):
        """
        初始化编排器

        Args:
            client: Kibana 客户端
            loader_classes: 加载器类列表，默认使用 ALL_LOADERS
            max_workers: 并发线程数，默认 5
        """
        self.client = client
        self.max_workers = max_workers

        if loader_classes is None:
            loader_classes = ALL_LOADERS
        self.loaders: List[LogLoader] = [cls() for cls in loader_classes]

    def _load_single(self, loader: LogLoader, ctx: TraceContext) -> LogLoader:
        """加载单个 loader（用于并发执行）"""
        loader.load(ctx, self.client)
        return loader

    def _get_loader(self, name: str) -> Optional[LogLoader]:
        """按名称查找已经注册的 loader 实例。"""
        for loader in self.loaders:
            if loader.name == name:
                return loader
        return None

    def _should_prefetch_assistant_runtime(self, ctx: TraceContext) -> bool:
        """判断是否值得先用 assistant_runtime 最小查询补齐依赖 ID。"""
        if not (ctx.session_id or ctx.conversation_id):
            return False
        if ctx.account_id and not (ctx.session_id or ctx.conversation_id):
            return False

        for loader_name, attr_name in self.ASSISTANT_RUNTIME_ID_DEPENDENT_LOADERS.items():
            if ctx.is_loader_enabled(loader_name) and not getattr(ctx, attr_name, None):
                return True
        return False

    def _prefetch_assistant_runtime_context(self, ctx: TraceContext) -> None:
        """用最小 assistant_runtime 查询预热 context，释放后续并发波次。"""
        if not self._should_prefetch_assistant_runtime(ctx):
            return

        runtime_loader = self._get_loader("assistant_runtime")
        if runtime_loader is None:
            runtime_loader = AssistantRuntimeLoader()
        if not isinstance(runtime_loader, AssistantRuntimeLoader):
            return

        query = runtime_loader.build_query(ctx)
        if not query:
            return

        start_time = parse_time_range(ctx.time_range) if ctx.time_range else None
        end_time = "now" if ctx.time_range else None
        prefetch_size = min(ctx.size, self.ASSISTANT_RUNTIME_PREFETCH_SIZE)

        print("   Prefetching assistant_runtime metadata...")
        try:
            result = self.client.search(
                query=query,
                index=runtime_loader.index_pattern,
                start_time=start_time,
                end_time=end_time,
                size=prefetch_size,
                sort=[{"@timestamp": {"order": "asc"}}],
                source_includes=runtime_loader.get_meta_source_includes(),
            )
            hits = result.get("hits", {}).get("hits", [])
            logs = [hit.get("_source", {}) for hit in hits]
            runtime_loader.extract_context_from_logs(ctx, logs)
        except Exception as e:
            print(f"   ⚠️  assistant_runtime metadata prefetch failed: {e}", file=sys.stderr)

    def trace(self, ctx: TraceContext) -> TraceContext:
        """执行追踪，按依赖顺序执行所有可执行的 loader（同一轮内并发）"""
        pending: Set[LogLoader] = set(self.loaders)
        completed: Set[str] = set()
        max_iterations = len(self.loaders) + 1

        print(f"🔍 Starting trace...")
        if ctx.session_id:
            print(f"   Session ID: {ctx.session_id}")
        if ctx.conversation_id:
            print(f"   Conversation ID: {ctx.conversation_id}")

        self._prefetch_assistant_runtime_context(ctx)

        for iteration in range(max_iterations):
            ready = [loader for loader in pending if loader.can_load(ctx)]

            if not ready:
                break

            loader_names = [l.name for l in ready]
            print(f"\n   === Round {iteration + 1}: {', '.join(loader_names)} ===")

            if len(ready) == 1:
                # 单个 loader，直接执行
                loader = ready[0]
                print(f"   Loading {loader.name}...")
                loader.load(ctx, self.client)
                loader.post_load(ctx)
                pending.discard(loader)
                completed.add(loader.name)
            else:
                # 多个 loader，并发执行
                with ThreadPoolExecutor(max_workers=min(self.max_workers, len(ready))) as executor:
                    futures = {
                        executor.submit(self._load_single, loader, ctx): loader
                        for loader in ready
                    }

                    for future in as_completed(futures):
                        loader = futures[future]
                        try:
                            future.result()
                            pending.discard(loader)
                            completed.add(loader.name)
                        except Exception as e:
                            print(f"   ⚠️  Error loading {loader.name}: {e}", file=sys.stderr)

                # post_load 顺序执行（可能会修改 ctx）
                for loader in ready:
                    if loader.name in completed:
                        loader.post_load(ctx)

        skipped = [
            loader.name for loader in pending
            if ctx.is_loader_enabled(loader.name)
        ]
        if skipped:
            print(f"\n   ⚠️  Skipped (dependencies not met): {', '.join(skipped)}",
                  file=sys.stderr)

        print(f"\n   📊 Total: {ctx.get_total_logs()} logs")

        return ctx
    
    def trace_by_session(
        self,
        session_id: str,
        time_range: Optional[str] = None,
        enabled_loaders: Optional[Set[str]] = None,
        size: int = 10000,
    ) -> TraceContext:
        """根据 session_id 追踪"""
        ctx = TraceContext(
            session_id=session_id,
            time_range=time_range,
            enabled_loaders=enabled_loaders or set(),
            size=size,
        )
        return self.trace(ctx)
    
    def trace_by_conversation(
        self,
        conversation_id: str,
        time_range: Optional[str] = None,
        enabled_loaders: Optional[Set[str]] = None,
        size: int = 10000,
    ) -> TraceContext:
        """
        根据 conversation_id 追踪

        如果提供的 ID 不是有效的 conversationId（首次搜索返回 0 条结果），
        会自动使用全文搜索来查找真正的 conversationId。
        """
        ctx = TraceContext(
            conversation_id=conversation_id,
            time_range=time_range,
            enabled_loaders=enabled_loaders or set(),
            size=size,
        )

        # 先尝试正常追踪
        ctx = self.trace(ctx)

        # 如果没有找到任何日志，尝试智能回退
        if ctx.get_total_logs() == 0:
            real_conv_id = self._find_real_conversation_id(conversation_id, time_range)
            if real_conv_id and real_conv_id != conversation_id:
                print(f"\n🔄 ID '{conversation_id}' is not a conversationId")
                print(f"   Found real conversationId: {real_conv_id}")
                print(f"   Retrying trace...")
                # 重新追踪
                ctx = TraceContext(
                    conversation_id=real_conv_id,
                    time_range=time_range,
                    enabled_loaders=enabled_loaders or set(),
                    size=size,
                )
                ctx = self.trace(ctx)

        return ctx

    def _find_real_conversation_id(
        self,
        search_id: str,
        time_range: Optional[str] = None
    ) -> Optional[str]:
        """
        使用全文搜索查找真正的 conversationId

        当用户提供的 ID 可能是 completionId 或其他 ID 时，
        使用全文搜索找到包含该 ID 的日志，并提取真正的 conversationId。
        """
        try:
            from ..kibana_client import parse_time_range
        except ImportError:
            from kibana_client import parse_time_range

        start_time = None
        end_time = None
        if time_range:
            start_time = parse_time_range(time_range)
            end_time = "now"

        # 使用全文搜索
        result = self.client.search(
            query=f'"{search_id}"',
            index="*:*-logs-air_assistant_runtime-*",
            start_time=start_time,
            end_time=end_time,
            size=1,
        )

        hits = result.get("hits", {}).get("hits", [])
        if not hits:
            return None

        # 从日志中提取真正的 conversationId
        source = hits[0].get("_source", {})
        conv_id = source.get("conversationId")

        return conv_id
