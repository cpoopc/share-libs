import time

from logtracer_extractors.iva.index_resolver import IndexResolver


class FakeClient:
    def __init__(self) -> None:
        self.search_calls: list[dict[str, object]] = []
        self.count_calls: list[tuple[str, str]] = []

    def resolve_indices(self, pattern: str) -> dict[str, list[str]]:
        if pattern == "*:*-logs-air_assistant_runtime-*":
            return {
                "indices": ["logs-air_assistant_runtime-2026.04.12"],
                "aliases": [],
                "data_streams": [],
            }
        if pattern == "*:*-logs-air_agent_service-*":
            return {"indices": [], "aliases": [], "data_streams": []}
        if pattern == "*:*-logs-nca-*":
            raise Exception("Connection error: timed out")
        if pattern == "*:*-logs-aig-*":
            raise Exception("HTTP 401: Unauthorized")
        raise AssertionError(f"Unexpected pattern: {pattern}")

    def search(self, query: str, index: str | None = None, size: int = 100, **kwargs) -> dict:
        self.search_calls.append(
            {
                "query": query,
                "index": index or "",
                "size": size,
                "kwargs": kwargs,
            }
        )
        if index == "*:*-logs-air_assistant_runtime-*":
            return {
                "hits": {
                    "hits": [
                        {"_id": "runtime-1", "_index": "logs-air_assistant_runtime-2026.04.12"}
                    ]
                }
            }
        if index == "*:*-logs-air_agent_service-*":
            return {"hits": {"hits": []}}
        if index == "*:*-logs-nca-*":
            raise Exception("Connection error: timed out")
        if index == "*:*-logs-aig-*":
            raise Exception("HTTP 401: Unauthorized")
        return {"hits": {"hits": []}}

    def count(self, query: str = "*", index: str | None = None, **kwargs) -> int:
        self.count_calls.append((query, index or ""))
        if index == "*:*-logs-air_assistant_runtime-*":
            return 7
        return 0


def test_index_resolver_classifies_component_probe_results() -> None:
    resolver = IndexResolver(FakeClient())

    runtime = resolver.resolve_component("assistant_runtime")
    agent_service = resolver.resolve_component("agent_service")
    nca = resolver.resolve_component("nca")
    aig = resolver.resolve_component("aig")

    assert runtime.status == "matched"
    assert runtime.resolved_indices == ["logs-air_assistant_runtime-2026.04.12"]
    assert runtime.queryable_patterns == []
    assert runtime.probe_hit_count == 1

    assert agent_service.status == "empty"
    assert agent_service.resolved_indices == []
    assert agent_service.queryable_patterns == []
    assert agent_service.probe_hit_count == 0

    assert nca.status == "unreachable"
    assert "timed out" in (nca.error or "")

    assert aig.status == "auth_error"
    assert "401" in (aig.error or "")


def test_index_resolver_caches_probe_results() -> None:
    client = FakeClient()
    resolver = IndexResolver(client)

    first = resolver.resolve_component("assistant_runtime")
    second = resolver.resolve_component("assistant_runtime")

    assert first is second
    assert client.search_calls == [
        {
            "query": "*",
            "index": "*:*-logs-air_assistant_runtime-*",
            "size": 1,
            "kwargs": {
                "source_includes": ["@timestamp"],
                "source_excludes": ["*"],
                "sort": [],
                "track_total_hits": False,
                "terminate_after": 1,
            },
        }
    ]
    assert client.count_calls == []


class FakeFallbackClient:
    def __init__(self) -> None:
        self.search_calls: list[dict[str, object]] = []

    def resolve_indices(self, pattern: str) -> dict[str, list[str]]:
        return {"indices": [], "aliases": [], "data_streams": []}

    def search(self, query: str, index: str | None = None, size: int = 100, **kwargs) -> dict:
        self.search_calls.append(
            {
                "query": query,
                "index": index or "",
                "size": size,
                "kwargs": kwargs,
            }
        )
        if index == "*:*-logs-gmg-*":
            return {"hits": {"hits": [{"_id": "gmg-1"}]}}
        return {"hits": {"hits": []}}


def test_index_resolver_falls_back_to_queryable_patterns_when_resolve_index_returns_empty() -> None:
    client = FakeFallbackClient()
    resolver = IndexResolver(client)

    gmg = resolver.resolve_component("gmg")

    assert gmg.status == "matched"
    assert gmg.resolved_indices == []
    assert gmg.queryable_patterns == ["*:*-logs-gmg-*"]
    assert gmg.probe_hit_count == 1
    assert client.search_calls == [
        {
            "query": "*",
            "index": "*:*-logs-gmg-*",
            "size": 1,
            "kwargs": {
                "source_includes": ["@timestamp"],
                "source_excludes": ["*"],
                "sort": [],
                "track_total_hits": False,
                "terminate_after": 1,
            },
        }
    ]


class FakeSharedPatternClient:
    def __init__(self) -> None:
        self.search_calls: list[str] = []

    def search(self, query: str, index: str | None = None, size: int = 100, **kwargs) -> dict:
        self.search_calls.append(index or "")
        return {
            "hits": {
                "hits": [
                    {"_id": "cprc-1", "_index": "logs-acc-ai-cprc-2026.04.12"}
                ]
            }
        }


def test_index_resolver_reuses_pattern_probe_results_for_shared_patterns() -> None:
    client = FakeSharedPatternClient()
    resolver = IndexResolver(client)

    srs = resolver.resolve_component("cprc_srs")
    sgs = resolver.resolve_component("cprc_sgs")

    assert srs.resolved_indices == ["logs-acc-ai-cprc-2026.04.12"]
    assert sgs.resolved_indices == ["logs-acc-ai-cprc-2026.04.12"]
    assert client.search_calls == ["*:*-ai-cprc*"]


class SlowProbeClient:
    def __init__(self) -> None:
        self.search_calls: list[str] = []

    def search(self, query: str, index: str | None = None, size: int = 100, **kwargs) -> dict:
        self.search_calls.append(index or "")
        time.sleep(0.1)
        return {
            "hits": {
                "hits": [
                    {"_id": "probe-1", "_index": f"{(index or '*').replace('*', 'x')}-resolved"}
                ]
            }
        }


def test_index_resolver_prewarms_unique_patterns_concurrently() -> None:
    client = SlowProbeClient()
    resolver = IndexResolver(client)

    start = time.perf_counter()
    resolver.prewarm_components(
        ["assistant_runtime", "agent_service", "nca", "aig", "cprc_srs", "cprc_sgs"],
        max_workers=4,
    )
    elapsed = time.perf_counter() - start

    assert len(client.search_calls) == 5
    assert elapsed < 0.35
