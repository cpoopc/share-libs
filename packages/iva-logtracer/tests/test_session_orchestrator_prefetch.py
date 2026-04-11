import threading
import time
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from logtracer_extractors.iva.loaders import (
    AgentServiceLoader,
    AssistantRuntimeLoader,
    CPRCSGSLoader,
    CPRCSRSLoader,
    NCALoader,
)
from logtracer_extractors.iva.orchestrator import SessionTraceOrchestrator


class FakeParallelClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._lock = threading.Lock()
        self.full_runtime_started = threading.Event()
        self.full_runtime_finished = threading.Event()
        self.parallel_queries_seen = False

    def search(self, **kwargs) -> dict:
        with self._lock:
            self.calls.append(kwargs)

        index = kwargs["index"]
        query = kwargs["query"]
        source_includes = kwargs.get("source_includes")

        if index == "*:*-logs-air_assistant_runtime-*":
            if source_includes:
                return {
                    "hits": {
                        "hits": [
                            {
                                "_source": {
                                    "@timestamp": "2026-04-02T00:00:00.100Z",
                                    "sessionId": "s-test",
                                    "conversationId": "c-test",
                                    "accountId": "123",
                                    "message": 'Speech recognition started: {"srsSessionId":"srs-test"}',
                                }
                            },
                            {
                                "_source": {
                                    "@timestamp": "2026-04-02T00:00:00.200Z",
                                    "sessionId": "s-test",
                                    "conversationId": "c-test",
                                    "accountId": "123",
                                    "message": 'Speech generation started: {"srsSessionId":"sgs-test"}',
                                }
                            },
                        ]
                    }
                }

            self.full_runtime_started.set()
            time.sleep(0.15)
            self.full_runtime_finished.set()
            return {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "@timestamp": "2026-04-02T00:00:00.100Z",
                                "sessionId": "s-test",
                                "conversationId": "c-test",
                                "accountId": "123",
                                "message": "full runtime log",
                            }
                        }
                    ]
                }
            }

        if self.full_runtime_started.wait(timeout=0.2) and not self.full_runtime_finished.is_set():
            self.parallel_queries_seen = True

        if index == "*:*-logs-air_agent_service-*":
            assert query == 'conversationId:"c-test"'
            return {"hits": {"hits": [{"_source": {"@timestamp": "2026-04-02T00:00:01.000Z", "message": "agent"}}]}}
        if index == "*:*-logs-nca-*":
            assert query == 'conversation_id:"c-test"'
            return {"hits": {"hits": [{"_source": {"@timestamp": "2026-04-02T00:00:01.100Z", "message": "nca"}}]}}
        if index == "*:*-ai-cprc*":
            assert query in {'message:"srs-test"', 'message:"sgs-test"'}
            return {"hits": {"hits": [{"_source": {"@timestamp": "2026-04-02T00:00:01.200Z", "message": "cprc"}}]}}

        raise AssertionError(f"unexpected search call: {kwargs}")


def test_trace_by_session_prefetches_runtime_metadata_and_unlocks_parallel_wave() -> None:
    client = FakeParallelClient()
    orchestrator = SessionTraceOrchestrator(
        client,
        loader_classes=[
            AssistantRuntimeLoader,
            AgentServiceLoader,
            NCALoader,
            CPRCSRSLoader,
            CPRCSGSLoader,
        ],
        max_workers=5,
    )

    ctx = orchestrator.trace_by_session(
        session_id="s-test",
        time_range="1h",
        enabled_loaders={"assistant_runtime", "agent_service", "nca", "cprc_srs", "cprc_sgs"},
        size=5000,
    )

    assistant_runtime_calls = [
        call for call in client.calls if call["index"] == "*:*-logs-air_assistant_runtime-*"
    ]

    assert ctx.conversation_id == "c-test"
    assert ctx.srs_session_id == "srs-test"
    assert ctx.sgs_session_id == "sgs-test"
    assert len(assistant_runtime_calls) == 2
    assert assistant_runtime_calls[0]["source_includes"] == AssistantRuntimeLoader.META_SOURCE_INCLUDES
    assert assistant_runtime_calls[0]["sort"] == [{"@timestamp": {"order": "asc"}}]
    assert "assistant_runtime_meta" not in ctx.logs
    assert set(ctx.logs) == {"assistant_runtime", "agent_service", "nca", "cprc_srs", "cprc_sgs"}
    assert client.parallel_queries_seen is True


def test_trace_by_session_can_use_hidden_prefetch_without_full_runtime_loader() -> None:
    client = FakeParallelClient()
    orchestrator = SessionTraceOrchestrator(
        client,
        loader_classes=[
            AssistantRuntimeLoader,
            NCALoader,
            CPRCSGSLoader,
        ],
        max_workers=3,
    )

    ctx = orchestrator.trace_by_session(
        session_id="s-test",
        time_range="1h",
        enabled_loaders={"nca", "cprc_sgs"},
        size=5000,
    )

    assistant_runtime_calls = [
        call for call in client.calls if call["index"] == "*:*-logs-air_assistant_runtime-*"
    ]

    assert ctx.conversation_id == "c-test"
    assert ctx.sgs_session_id == "sgs-test"
    assert len(assistant_runtime_calls) == 1
    assert assistant_runtime_calls[0]["source_includes"] == AssistantRuntimeLoader.META_SOURCE_INCLUDES
    assert "assistant_runtime" not in ctx.logs
    assert set(ctx.logs) == {"nca", "cprc_sgs"}
