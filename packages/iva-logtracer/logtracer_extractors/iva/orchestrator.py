#!/usr/bin/env python3
"""
IVA SessionTraceOrchestrator - IVA 会话追踪编排器

按依赖顺序执行 LogLoaders，自动处理依赖关系
支持并发加载以提高速度
"""

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, List, Optional, Set, Type

try:
    from ..kibana_client import KibanaClient
    from ..kibana_client import parse_time_range
    from ..loaders import LogLoader
    from .loaders import ALL_LOADERS
    from .loaders.assistant_runtime import AssistantRuntimeLoader
    from .trace_context import TraceContext
    from ..nova.loaders import NCALoader
except ImportError:
    from kibana_client import KibanaClient, parse_time_range
    from loaders import ALL_LOADERS, LogLoader
    from loaders.assistant_runtime import AssistantRuntimeLoader
    from trace_context import TraceContext
    from nova.loaders import NCALoader


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
    NCA_REQUEST_ID_PREFETCH_SIZE = 500
    NCA_REQUEST_ID_DEPENDENT_LOADERS = {"aig", "gmg"}

    def __init__(
        self,
        client: KibanaClient,
        loader_classes: Optional[List[Type[LogLoader]]] = None,
        max_workers: int = 5,
        loader_clients: Optional[dict[str, Any]] = None,
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
        self.loader_clients = dict(loader_clients or {})

        if loader_classes is None:
            loader_classes = ALL_LOADERS
        self.loaders: List[LogLoader] = [cls() for cls in loader_classes]

    def _get_client_for_loader(self, loader: LogLoader) -> Any:
        """Return the component-specific client when configured."""
        return self.loader_clients.get(loader.name, self.client)

    def _load_single(self, loader: LogLoader, ctx: TraceContext) -> LogLoader:
        """加载单个 loader（用于并发执行）"""
        loader.load(ctx, self._get_client_for_loader(loader))
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
        prefetch_size = self._get_assistant_runtime_prefetch_size(ctx)

        print("   Prefetching assistant_runtime metadata...")
        try:
            search_params = {
                "query": query,
                "index": runtime_loader.index_pattern,
                "start_time": start_time,
                "end_time": end_time,
                "size": prefetch_size,
            }
            search_params["sort"] = [{"@timestamp": {"order": "asc"}}]
            search_params["source_includes"] = runtime_loader.get_meta_source_includes()

            result = self.client.search(**search_params)
            hits = result.get("hits", {}).get("hits", [])
            logs = [hit.get("_source", {}) for hit in hits]
            runtime_loader.extract_context_from_logs(ctx, logs)
            if self._can_reuse_assistant_runtime_prefetch(ctx, logs):
                ctx.store_prefetched_logs(runtime_loader.name, logs[: ctx.size])
        except Exception as e:
            print(f"   ⚠️  assistant_runtime metadata prefetch failed: {e}", file=sys.stderr)

    def _get_assistant_runtime_prefetch_size(self, ctx: TraceContext) -> int:
        """metadata prefetch 维持轻量窗口，避免把优化变成回归。"""
        return min(ctx.size, self.ASSISTANT_RUNTIME_PREFETCH_SIZE)

    def _has_conversation_dependent_loaders(self, ctx: TraceContext) -> bool:
        """conversation_id 链路更依赖 full runtime 结果，避免误复用 metadata。"""
        for loader_name, attr_name in self.ASSISTANT_RUNTIME_ID_DEPENDENT_LOADERS.items():
            if attr_name == "conversation_id" and ctx.is_loader_enabled(loader_name):
                return True
        return False

    def _can_reuse_assistant_runtime_prefetch(
        self,
        ctx: TraceContext,
        logs: list[dict],
    ) -> bool:
        """prefetch 已满足当前链路依赖时，才允许跳过 full runtime query。"""
        if not logs:
            return False
        if not ctx.is_loader_enabled("assistant_runtime"):
            return False
        if ctx.size > self.ASSISTANT_RUNTIME_PREFETCH_SIZE:
            return False
        if self._has_conversation_dependent_loaders(ctx):
            return False

        for loader_name, attr_name in self.ASSISTANT_RUNTIME_ID_DEPENDENT_LOADERS.items():
            if ctx.is_loader_enabled(loader_name) and not getattr(ctx, attr_name, None):
                return False
        return True

    def _should_reuse_assistant_runtime_prefetch(self, ctx: TraceContext) -> bool:
        """小 size 场景直接复用 prefetch，避免 assistant_runtime 双查。"""
        if ctx.size > self.ASSISTANT_RUNTIME_PREFETCH_SIZE:
            return False
        if not ctx.is_loader_enabled("assistant_runtime"):
            return False
        return bool(ctx.prefetched_logs.get("assistant_runtime"))

    def _promote_prefetched_assistant_runtime(
        self,
        ctx: TraceContext,
        pending: Set[LogLoader],
        completed: Set[str],
    ) -> None:
        """将隐藏 prefetch 结果提升为正式 assistant_runtime 输出。"""
        if not self._should_reuse_assistant_runtime_prefetch(ctx):
            return

        runtime_loader = self._get_loader("assistant_runtime")
        if runtime_loader is None or runtime_loader not in pending:
            return

        logs = ctx.consume_prefetched_logs(runtime_loader.name)
        if not logs:
            return

        ctx.logs[runtime_loader.name] = logs
        pending.discard(runtime_loader)
        completed.add(runtime_loader.name)
        print(f"   📊 {runtime_loader.name}: {len(logs)} logs (reused prefetch)")

    def _should_prefetch_nca_request_ids(self, ctx: TraceContext) -> bool:
        """小窗口 Nova 链路先隐藏预取 request_id，避免下游关联被采样截断。"""
        if not ctx.conversation_id:
            return False
        if ctx.size >= self.NCA_REQUEST_ID_PREFETCH_SIZE:
            return False
        if ctx.logs.get("nca"):
            return False
        if ctx.get_prefetched_request_ids("nca"):
            return False
        return any(
            ctx.is_loader_enabled(loader_name)
            for loader_name in self.NCA_REQUEST_ID_DEPENDENT_LOADERS
        )

    def _prefetch_nca_request_ids(self, ctx: TraceContext) -> None:
        """隐藏预取 NCA request_id，只服务于下游 AIG/GMG 关联。"""
        if not self._should_prefetch_nca_request_ids(ctx):
            return

        nca_loader = self._get_loader("nca")
        if nca_loader is None:
            nca_loader = NCALoader()
        if not isinstance(nca_loader, NCALoader):
            return

        query = nca_loader.build_query(ctx)
        if not query:
            return

        start_time = parse_time_range(ctx.time_range) if ctx.time_range else None
        end_time = "now" if ctx.time_range else None

        print("   Prefetching nca request_ids...")
        try:
            result = self._get_client_for_loader(nca_loader).search(
                query=query,
                index=nca_loader.index_pattern,
                start_time=start_time,
                end_time=end_time,
                size=self.NCA_REQUEST_ID_PREFETCH_SIZE,
                sort=[{"@timestamp": {"order": "asc"}}],
                source_includes=nca_loader.get_request_id_source_includes(),
            )
            hits = result.get("hits", {}).get("hits", [])
            logs = [hit.get("_source", {}) for hit in hits]
            request_ids = nca_loader.extract_request_ids_from_logs(logs)
            if request_ids:
                ctx.store_prefetched_request_ids(nca_loader.name, request_ids)
        except Exception as e:
            print(f"   ⚠️  nca request_id prefetch failed: {e}", file=sys.stderr)

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
        self._promote_prefetched_assistant_runtime(ctx, pending, completed)

        for iteration in range(max_iterations):
            self._prefetch_nca_request_ids(ctx)
            ready = [loader for loader in pending if loader.can_load(ctx)]

            if not ready:
                break

            loader_names = [l.name for l in ready]
            print(f"\n   === Round {iteration + 1}: {', '.join(loader_names)} ===")

            if len(ready) == 1:
                # 单个 loader，直接执行
                loader = ready[0]
                print(f"   Loading {loader.name}...")
                loader.load(ctx, self._get_client_for_loader(loader))
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
