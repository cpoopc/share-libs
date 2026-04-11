from cptools_kibana.client import KibanaClient, KibanaConfig
from unittest.mock import Mock


def test_search_includes_search_after_and_custom_sort(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_request(method: str, path: str, body: dict | None = None) -> dict:
        captured["method"] = method
        captured["path"] = path
        captured["body"] = body or {}
        return {}

    client = KibanaClient(KibanaConfig(url="https://example.com", username="u", password="p"))
    monkeypatch.setattr(client, "_request", fake_request)

    client.search(
        query='accountId:"1"',
        index="*:*-logs-air_assistant_runtime-*",
        size=500,
        sort=[{"@timestamp": {"order": "asc"}}, {"_id": {"order": "asc"}}],
        search_after=["2026-03-18T00:00:00Z", "doc-1"],
    )

    assert captured["method"] == "POST"
    assert captured["path"] == "*:*-logs-air_assistant_runtime-*/_search"
    assert captured["body"]["search_after"] == ["2026-03-18T00:00:00Z", "doc-1"]


def test_fetch_all_hits_uses_search_after_until_last_page() -> None:
    from logtracer_extractors.iva.discovery.service import fetch_all_hits

    client = Mock()
    client.count.return_value = 3
    client.search.side_effect = [
        {
            "hits": {
                "hits": [
                    {"sort": ["2026-03-18T00:00:01Z", "doc-1"], "_source": {"sessionId": "s-1"}},
                    {"sort": ["2026-03-18T00:00:02Z", "doc-2"], "_source": {"sessionId": "s-2"}},
                ]
            }
        },
        {
            "hits": {
                "hits": [
                    {"sort": ["2026-03-18T00:00:03Z", "doc-3"], "_source": {"sessionId": "s-3"}},
                ]
            }
        },
    ]

    result = fetch_all_hits(
        client=client,
        query='accountId:"1"',
        index="*:*-logs-air_assistant_runtime-*",
        start_time="now-3d",
        end_time="now",
        page_size=2,
        max_pages=5,
    )

    assert len(result.hits) == 3
    assert result.page_count == 2
    assert result.total_hits == 3
    assert client.search.call_args_list[1].kwargs["search_after"] == [
        "2026-03-18T00:00:02Z",
        "doc-2",
    ]
