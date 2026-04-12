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
from logtracer_extractors.nova.loaders.aig import AIGLoader
from logtracer_extractors.nova.loaders.gmg import GMGLoader


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
                assert kwargs["sort"] == [{"@timestamp": {"order": "asc"}}]
                if kwargs["size"] <= 5:
                    return {
                        "hits": {
                            "hits": [
                                {
                                    "_source": {
                                        "@timestamp": "2026-04-12T00:00:00.100Z",
                                        "sessionId": "s-cross",
                                        "accountId": "123",
                                        "message": "runtime prefetch",
                                    }
                                }
                            ]
                        }
                    }
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


class FakeCrossComponentClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def search(self, **kwargs) -> dict:
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
                                    "@timestamp": "2026-04-12T00:00:00.100Z",
                                    "sessionId": "s-cross",
                                    "accountId": "123",
                                    "message": "runtime prefetch",
                                }
                            },
                            {
                                "_source": {
                                    "@timestamp": "2026-04-12T00:00:00.200Z",
                                    "sessionId": "s-cross",
                                    "conversationId": "c-cross",
                                    "accountId": "123",
                                    "message": "runtime prefetch with conversation",
                                }
                            }
                        ]
                    }
                }

            assert query == 'sessionId:"s-cross"'
            return {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "@timestamp": "2026-04-12T00:00:00.100Z",
                                "sessionId": "s-cross",
                                "conversationId": "c-cross",
                                "accountId": "123",
                                "message": "runtime full",
                            }
                        }
                    ]
                }
            }

        if index == "*:*-logs-nca-*":
            assert query == 'conversation_id:"c-cross"'
            if kwargs["size"] < NCALoader.MIN_DOWNSTREAM_CORRELATION_SIZE:
                raise AssertionError(f"expected expanded nca size, got {kwargs['size']}")
            return {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "@timestamp": "2026-04-12T00:00:01.000Z",
                                "message": "nca",
                                "request_id": "req-123",
                            }
                        }
                    ]
                }
            }

        if index == "*:*-logs-aig-*":
            assert query == 'request_id:"req-123"'
            return {"hits": {"hits": [{"_source": {"@timestamp": "2026-04-12T00:00:01.100Z", "message": "aig"}}]}}

        if index == "*:*-logs-gmg-*":
            assert query == 'log_context_RCRequestId:"req-123"'
            return {"hits": {"hits": [{"_source": {"@timestamp": "2026-04-12T00:00:01.200Z", "message": "gmg"}}]}}

        raise AssertionError(f"unexpected search call: {kwargs}")


def test_trace_by_session_queries_nca_downstream_components() -> None:
    client = FakeCrossComponentClient()
    orchestrator = SessionTraceOrchestrator(
        client,
        loader_classes=[
            AssistantRuntimeLoader,
            NCALoader,
            AIGLoader,
            GMGLoader,
        ],
        max_workers=4,
    )

    ctx = orchestrator.trace_by_session(
        session_id="s-cross",
        time_range="1h",
        enabled_loaders={"assistant_runtime", "nca", "aig", "gmg"},
        size=5000,
    )

    called_indices = [call["index"] for call in client.calls]

    assert ctx.conversation_id == "c-cross"
    assert called_indices.count("*:*-logs-air_assistant_runtime-*") == 2
    assert "*:*-logs-nca-*" in called_indices
    assert "*:*-logs-aig-*" in called_indices
    assert "*:*-logs-gmg-*" in called_indices
    assert set(ctx.logs) == {"assistant_runtime", "nca", "aig", "gmg"}


def test_trace_by_session_falls_back_to_full_runtime_for_small_nova_chain() -> None:
    client = FakeCrossComponentClient()
    orchestrator = SessionTraceOrchestrator(
        client,
        loader_classes=[
            AssistantRuntimeLoader,
            NCALoader,
            AIGLoader,
            GMGLoader,
        ],
        max_workers=4,
    )

    ctx = orchestrator.trace_by_session(
        session_id="s-cross",
        time_range="1h",
        enabled_loaders={"assistant_runtime", "nca", "aig", "gmg"},
        size=5,
    )

    called_indices = [call["index"] for call in client.calls]
    assistant_runtime_calls = [
        call for call in client.calls if call["index"] == "*:*-logs-air_assistant_runtime-*"
    ]

    assert ctx.conversation_id == "c-cross"
    assert called_indices.count("*:*-logs-air_assistant_runtime-*") == 2
    assert assistant_runtime_calls[0]["source_includes"] == AssistantRuntimeLoader.META_SOURCE_INCLUDES
    assert assistant_runtime_calls[0]["sort"] == [{"@timestamp": {"order": "asc"}}]
    assert assistant_runtime_calls[0]["size"] == 5
    assert assistant_runtime_calls[1].get("source_includes") is None
    assert assistant_runtime_calls[1].get("sort") is None
    assert assistant_runtime_calls[1]["size"] == 5
    nca_calls = [call for call in client.calls if call["index"] == "*:*-logs-nca-*"]
    assert len(nca_calls) == 1
    assert nca_calls[0]["size"] == NCALoader.MIN_DOWNSTREAM_CORRELATION_SIZE
    assert "*:*-logs-aig-*" in called_indices
    assert "*:*-logs-gmg-*" in called_indices
    assert set(ctx.logs) == {"assistant_runtime", "nca", "aig", "gmg"}


class FakeVoiceChainClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def search(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        index = kwargs["index"]
        query = kwargs["query"]
        source_includes = kwargs.get("source_includes")

        if index == "*:*-logs-air_assistant_runtime-*":
            if source_includes:
                assert kwargs["sort"] == [{"@timestamp": {"order": "asc"}}]
                assert kwargs["size"] == 200
                return {
                    "hits": {
                        "hits": [
                            {
                                "_source": {
                                    "@timestamp": "2026-04-12T00:00:00.100Z",
                                    "sessionId": "s-voice",
                                    "conversationId": "c-voice",
                                    "accountId": "123",
                                    "message": 'Speech recognition started: {"srsSessionId":"srs-voice"}',
                                }
                            },
                            {
                                "_source": {
                                    "@timestamp": "2026-04-12T00:00:00.200Z",
                                    "sessionId": "s-voice",
                                    "conversationId": "c-voice",
                                    "accountId": "123",
                                    "message": 'Speech generation started: {"srsSessionId":"sgs-voice"}',
                                }
                            },
                        ]
                    }
                }

            raise AssertionError("small voice chain should reuse metadata prefetch")

        if index == "*:*-ai-cprc*":
            assert query in {'message:"srs-voice"', 'message:"sgs-voice"'}
            return {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "@timestamp": "2026-04-12T00:00:01.000Z",
                                "message": "cprc",
                            }
                        }
                    ]
                }
            }

        raise AssertionError(f"unexpected search call: {kwargs}")


def test_trace_by_session_reuses_prefetch_for_small_voice_chain() -> None:
    client = FakeVoiceChainClient()
    orchestrator = SessionTraceOrchestrator(
        client,
        loader_classes=[
            AssistantRuntimeLoader,
            CPRCSRSLoader,
            CPRCSGSLoader,
        ],
        max_workers=3,
    )

    ctx = orchestrator.trace_by_session(
        session_id="s-voice",
        time_range="1h",
        enabled_loaders={"assistant_runtime", "cprc_srs", "cprc_sgs"},
        size=200,
    )

    called_indices = [call["index"] for call in client.calls]
    assistant_runtime_calls = [
        call for call in client.calls if call["index"] == "*:*-logs-air_assistant_runtime-*"
    ]

    assert ctx.conversation_id == "c-voice"
    assert ctx.srs_session_id == "srs-voice"
    assert ctx.sgs_session_id == "sgs-voice"
    assert called_indices.count("*:*-logs-air_assistant_runtime-*") == 1
    assert assistant_runtime_calls[0]["source_includes"] == AssistantRuntimeLoader.META_SOURCE_INCLUDES
    assert assistant_runtime_calls[0]["sort"] == [{"@timestamp": {"order": "asc"}}]
    assert assistant_runtime_calls[0]["size"] == 200
    assert set(ctx.logs) == {"assistant_runtime", "cprc_srs", "cprc_sgs"}


class FakePrimaryNovaRoutingClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def search(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        index = kwargs["index"]
        source_includes = kwargs.get("source_includes")

        if index != "*:*-logs-air_assistant_runtime-*":
            raise AssertionError(f"primary client should not receive {index}")

        if source_includes:
            return {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "@timestamp": "2026-04-12T00:00:00.100Z",
                                "sessionId": "s-cross",
                                "conversationId": "c-cross",
                                "accountId": "123",
                                "message": "runtime prefetch with conversation",
                            }
                        }
                    ]
                }
            }

        return {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "@timestamp": "2026-04-12T00:00:00.100Z",
                            "sessionId": "s-cross",
                            "conversationId": "c-cross",
                            "accountId": "123",
                            "message": "runtime full",
                        }
                    }
                ]
            }
        }


class FakeOpsNovaRoutingClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def search(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        index = kwargs["index"]
        query = kwargs["query"]

        if index == "*:*-logs-nca-*":
            assert query == 'conversation_id:"c-cross"'
            return {
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "@timestamp": "2026-04-12T00:00:01.000Z",
                                "message": "nca",
                                "request_id": "req-123",
                            }
                        }
                    ]
                }
            }

        if index == "*:*-logs-aig-*":
            assert query == 'request_id:"req-123"'
            return {
                "hits": {
                    "hits": [
                        {"_source": {"@timestamp": "2026-04-12T00:00:01.100Z", "message": "aig"}}
                    ]
                }
            }

        if index == "*:*-logs-gmg-*":
            assert query == 'log_context_RCRequestId:"req-123"'
            return {
                "hits": {
                    "hits": [
                        {"_source": {"@timestamp": "2026-04-12T00:00:01.200Z", "message": "gmg"}}
                    ]
                }
            }

        raise AssertionError(f"ops client should not receive {index}")


def test_trace_by_session_routes_only_nova_components_to_ops_client() -> None:
    primary_client = FakePrimaryNovaRoutingClient()
    ops_client = FakeOpsNovaRoutingClient()
    orchestrator = SessionTraceOrchestrator(
        primary_client,
        loader_classes=[
            AssistantRuntimeLoader,
            NCALoader,
            AIGLoader,
            GMGLoader,
        ],
        max_workers=4,
        loader_clients={
            "nca": ops_client,
            "aig": ops_client,
            "gmg": ops_client,
        },
    )

    ctx = orchestrator.trace_by_session(
        session_id="s-cross",
        time_range="1h",
        enabled_loaders={"assistant_runtime", "nca", "aig", "gmg"},
        size=5000,
    )

    primary_indices = [call["index"] for call in primary_client.calls]
    ops_indices = [call["index"] for call in ops_client.calls]

    assert ctx.conversation_id == "c-cross"
    assert primary_indices == [
        "*:*-logs-air_assistant_runtime-*",
        "*:*-logs-air_assistant_runtime-*",
    ]
    assert sorted(ops_indices) == sorted([
        "*:*-logs-nca-*",
        "*:*-logs-aig-*",
        "*:*-logs-gmg-*",
    ])
