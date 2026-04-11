from pathlib import Path

from logtracer_extractors.iva.turn.analyzer import VoiceCallAnalyzer
from logtracer_extractors.iva.turn.models import Turn, parse_timestamp


def test_extract_simple_tool_call_captures_tool_type(tmp_path: Path) -> None:
    analyzer = VoiceCallAnalyzer(tmp_path)

    client_call = analyzer._extract_simple_tool_call("Calling client tool: air_searchCompanyKnowledgeBase")
    server_call = analyzer._extract_simple_tool_call("serverTool: calendar.lookup")

    assert client_call is not None
    assert client_call["tool_name"] == "air_searchCompanyKnowledgeBase"
    assert client_call["tool_type"] == "client"

    assert server_call is not None
    assert server_call["tool_name"] == "calendar.lookup"
    assert server_call["tool_type"] == "server"


def test_update_tool_call_preserves_tool_type_and_merges_lifecycle(tmp_path: Path) -> None:
    analyzer = VoiceCallAnalyzer(tmp_path)
    turn = Turn(turn_number=1, turn_type="user_turn")

    start_ts = "2026-03-24T10:00:00.000Z"
    end_ts = "2026-03-24T10:00:01.500Z"

    analyzer._update_tool_call(
        turn,
        {
            "tool_name": "calendar.lookup",
            "tool_call_id": "tool-1",
            "tool_type": "serverTool",
            "status": "unknown",
            "input": '{"date":"2026-03-24"}',
        },
        source_component="assistant_runtime",
        phase="start",
        ts_dt=parse_timestamp(start_ts),
        ts_str=start_ts,
    )
    analyzer._update_tool_call(
        turn,
        {
            "tool_name": "calendar.lookup",
            "tool_call_id": "tool-1",
            "tool_type": "serverTool",
            "status": "success",
            "output": '{"events":[]}',
        },
        source_component="assistant_runtime",
        phase="end",
        ts_dt=parse_timestamp(end_ts),
        ts_str=end_ts,
    )

    assert len(turn.tool_calls) == 1
    tool_call = turn.tool_calls[0]
    assert tool_call["tool_type"] == "server"
    assert tool_call["status"] == "success"
    assert tool_call["start_timestamp"] == start_ts
    assert tool_call["end_timestamp"] == end_ts
    assert tool_call["duration_ms"] == 1500.0
    assert tool_call["input"] == '{"date":"2026-03-24"}'
    assert tool_call["output"] == '{"events":[]}'


def test_extract_trace_tool_call_normalizes_nca_patterns(tmp_path: Path) -> None:
    analyzer = VoiceCallAnalyzer(tmp_path)

    start = analyzer._extract_trace_tool_call(
        "[Trace][Tool] Started: toolName=air_searchCompanyKnowledgeBase, toolType=Integration, callId=call_123"
    )
    end = analyzer._extract_trace_tool_call(
        "[Tool][transfer_call] callTool completed, success: false"
    )

    assert start is not None
    assert start["tool_name"] == "air_searchCompanyKnowledgeBase"
    assert start["tool_type"] == "server"
    assert start["tool_call_id"] == "call_123"

    assert end is not None
    assert end["tool_name"] == "transfer_call"
    assert end["status"] == "failed"
