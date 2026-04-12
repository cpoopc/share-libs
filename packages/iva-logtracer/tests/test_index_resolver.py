from logtracer_extractors.iva.index_resolver import IndexResolver


class FakeClient:
    def __init__(self) -> None:
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
    assert runtime.document_count == 7

    assert agent_service.status == "empty"
    assert agent_service.resolved_indices == []
    assert agent_service.document_count == 0

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
    assert client.count_calls == [("*", "*:*-logs-air_assistant_runtime-*")]
