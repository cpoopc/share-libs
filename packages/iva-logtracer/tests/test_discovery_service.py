from logtracer_extractors.iva.discovery.models import (
    DiscoveryRequest,
    DiscoveryResult,
    DiscoverySession,
    DiscoveryStats,
)
from logtracer_extractors.iva.discovery.renderers import (
    render_discovery_json,
    render_discovery_markdown,
)
from logtracer_extractors.iva.discovery.service import (
    aggregate_sessions,
    select_evidence_lines,
)


def test_discovery_result_shape_is_serializable() -> None:
    result = DiscoveryResult(
        query=DiscoveryRequest(
            env="lab",
            index="*:*-logs-air_assistant_runtime-*",
            field="accountId",
            value="1",
            query=None,
            session_key="sessionId",
            page_size=500,
            max_pages=50,
            start_time="now-3d",
            end_time="now",
        ),
        stats=DiscoveryStats(
            total_hits=2,
            fetched_hits=2,
            page_size=500,
            page_count=1,
            session_count=1,
            complete=True,
        ),
        sessions=[
            DiscoverySession(
                session_id="s-1",
                first_timestamp="2026-03-18T00:00:01Z",
                last_timestamp="2026-03-18T00:00:02Z",
                log_count=2,
            )
        ],
    )

    payload = result.to_dict()

    assert payload["stats"]["complete"] is True
    assert payload["sessions"][0]["sessionId"] == "s-1"
    assert payload["query"]["query_mode"] == "field_value"
    assert payload["query"]["time_range"]["last"] == "3d"


def test_aggregate_sessions_merges_hits_by_session_and_fills_summary_fields() -> None:
    sessions = aggregate_sessions(
        hits=[
            {
                "_source": {
                    "@timestamp": "2026-03-18T00:00:01Z",
                    "sessionId": "s-1",
                    "conversationId": "c-1",
                    "message": "Start processing task",
                    "accountId": "1",
                }
            },
            {
                "_source": {
                    "@timestamp": "2026-03-18T00:00:02Z",
                    "sessionId": "s-1",
                    "taskId": "t-1",
                    "message": "Created new Conversation",
                    "accountId": "1",
                }
            },
        ],
        session_key="sessionId",
        matched_field_name="accountId",
    )

    assert len(sessions) == 1
    assert sessions[0].log_count == 2
    assert sessions[0].conversation_id == "c-1"
    assert sessions[0].task_id == "t-1"
    assert sessions[0].matched_fields == {"accountId": "1"}
    assert len(sessions[0].evidence) >= 1


def test_render_discovery_markdown_contains_query_stats_and_session_rows() -> None:
    result = DiscoveryResult(
        query=DiscoveryRequest(
            env="lab",
            index="*:*-logs-air_assistant_runtime-*",
            field="accountId",
            value="1",
            query=None,
            session_key="sessionId",
            page_size=500,
            max_pages=50,
            start_time="now-3d",
            end_time="now",
        ),
        stats=DiscoveryStats(
            total_hits=2,
            fetched_hits=2,
            page_size=500,
            page_count=1,
            session_count=1,
            complete=True,
        ),
        sessions=[
            DiscoverySession(
                session_id="s-1",
                first_timestamp="2026-03-18T00:00:01Z",
                last_timestamp="2026-03-18T00:00:02Z",
                log_count=2,
                evidence=["Created new Conversation"],
            )
        ],
    )

    markdown = render_discovery_markdown(result)
    json_payload = render_discovery_json(result)

    assert "# Discovery Results" in markdown
    assert "session_count" in markdown
    assert "s-1" in markdown
    assert '"sessionId": "s-1"' in json_payload
    assert '`field_value`' in markdown
    assert "`accountId` = `1`" in markdown


def test_select_evidence_lines_prefers_high_signal_messages() -> None:
    evidence = select_evidence_lines(
        [
            {"message": "plain startup noise"},
            {"message": "Created new Conversation abc"},
            {"message": "taskId=t-1"},
            {"message": "warn: backend returned retryable response"},
            {"message": "error while forwarding"},
        ]
    )

    assert "Created new Conversation abc" in evidence
    assert "error while forwarding" in evidence
    assert len(evidence) <= 4
