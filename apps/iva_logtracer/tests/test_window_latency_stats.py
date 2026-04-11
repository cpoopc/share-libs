import importlib.util
from pathlib import Path
import sys

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "window_latency_stats.py"

SPEC = importlib.util.spec_from_file_location("window_latency_stats", SCRIPT_PATH)
window_latency_stats = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
sys.modules["window_latency_stats"] = window_latency_stats
SPEC.loader.exec_module(window_latency_stats)


def _session(
    *,
    session_id: str,
    conversation_id: str,
    rows: list[dict],
    filler_turn_numbers: list[int],
) -> dict:
    return {
        "session_id": session_id,
        "conversation_id": conversation_id,
        "session_dir": f"/tmp/{session_id}-{conversation_id}",
        "turn_summary_matrix": rows,
        "manual_rca_view": {
            "filler_turns": [
                {"turn_number": turn_number, "segments_ms": {}}
                for turn_number in filler_turn_numbers
            ]
        },
    }


def test_summarize_metric_series_reports_percentiles_and_suspects() -> None:
    metric = window_latency_stats.METRIC_SPECS[0]

    summary = window_latency_stats._summarize_metric_series(
        metric=metric,
        values_ms=[100.0, 200.0, 400.0, 800.0, 1600.0],
        eligible_turn_count=6,
        total_user_turn_count=8,
    )

    assert summary["count"] == 5
    assert summary["eligible_turn_count"] == 6
    assert summary["total_user_turn_count"] == 8
    assert summary["coverage_rate"] == pytest.approx(5 / 6)
    assert summary["avg_ms"] == pytest.approx(620.0)
    assert summary["p50_ms"] == pytest.approx(400.0)
    assert summary["p90_ms"] == pytest.approx(1280.0)
    assert summary["p95_ms"] == pytest.approx(1440.0)
    assert summary["max_ms"] == pytest.approx(1600.0)
    assert "[SUSPECT] p95 >= 800 ms" in summary["markers"]
    assert "[SUSPECT] max >= 800 ms" in summary["markers"]


def test_aggregate_latency_window_stats_uses_user_and_filler_denominators() -> None:
    sessions = [
        _session(
            session_id="s-1",
            conversation_id="c-1",
            filler_turn_numbers=[2],
            rows=[
                {
                    "turn_number": 2,
                    "turn_type": "user_turn",
                    "transcript": "Need to change",
                    "ai_response": "Let me update that.",
                    "stt_lag_ms": 900.0,
                    "user_speak_end_to_filler_audible_ms": 1400.0,
                    "filler_audio_end_to_agent_audible_ms": 100.0,
                    "markers": ["[SUSPECT] STT lag"],
                },
                {
                    "turn_number": 3,
                    "turn_type": "user_turn_continued",
                    "transcript": "Yes",
                    "ai_response": "Done.",
                    "stt_lag_ms": 700.0,
                    "user_speak_end_to_filler_audible_ms": None,
                    "filler_audio_end_to_agent_audible_ms": None,
                    "markers": [],
                },
            ],
        ),
        _session(
            session_id="s-2",
            conversation_id="c-2",
            filler_turn_numbers=[3],
            rows=[
                {
                    "turn_number": 2,
                    "turn_type": "user_turn_interrupted",
                    "transcript": "Hello",
                    "ai_response": "Hi there.",
                    "stt_lag_ms": None,
                    "user_speak_end_to_filler_audible_ms": None,
                    "filler_audio_end_to_agent_audible_ms": None,
                    "markers": [],
                },
                {
                    "turn_number": 3,
                    "turn_type": "user_turn",
                    "transcript": "Transfer me",
                    "ai_response": "Connecting you now.",
                    "stt_lag_ms": 500.0,
                    "user_speak_end_to_filler_audible_ms": 2600.0,
                    "filler_audio_end_to_agent_audible_ms": 1200.0,
                    "markers": ["[SUSPECT] filler audio end -> agent audible"],
                },
            ],
        ),
    ]

    payload = window_latency_stats.aggregate_latency_window_stats(
        session_diagnostics=sessions,
        metadata={"source": "test"},
    )

    assert payload["session_count"] == 2
    assert payload["user_turn_count"] == 4
    assert payload["filler_turn_count"] == 2

    stt_stats = payload["metrics"]["user_speak_end_to_is_final_lag_ms"]
    assert stt_stats["count"] == 3
    assert stt_stats["eligible_turn_count"] == 4
    assert stt_stats["coverage_rate"] == pytest.approx(0.75)

    filler_stats = payload["metrics"]["user_speak_end_to_filler_audible_ms"]
    assert filler_stats["count"] == 2
    assert filler_stats["eligible_turn_count"] == 2
    assert filler_stats["coverage_rate"] == pytest.approx(1.0)
    assert "[SUSPECT] p95 >= 2500 ms" in filler_stats["markers"]

    gap_stats = payload["metrics"]["filler_audio_end_to_agent_audible_ms"]
    assert gap_stats["count"] == 2
    assert gap_stats["eligible_turn_count"] == 2
    assert gap_stats["max_ms"] == pytest.approx(1200.0)

    worst_gap_turn = payload["worst_turns"]["filler_audio_end_to_agent_audible_ms"][0]
    assert worst_gap_turn["session_id"] == "s-2"
    assert worst_gap_turn["turn_number"] == 3
    assert "[SUSPECT] filler audio end -> agent audible" in worst_gap_turn["markers"]


def test_render_markdown_includes_metric_markers_and_worst_turns() -> None:
    payload = window_latency_stats.aggregate_latency_window_stats(
        session_diagnostics=[
            _session(
                session_id="s-1",
                conversation_id="c-1",
                filler_turn_numbers=[2],
                rows=[
                    {
                        "turn_number": 2,
                        "turn_type": "user_turn",
                        "transcript": "Need help",
                        "ai_response": "I can help with that.",
                        "stt_lag_ms": 910.0,
                        "user_speak_end_to_filler_audible_ms": 2800.0,
                        "filler_audio_end_to_agent_audible_ms": 1500.0,
                        "markers": [
                            "[SUSPECT] STT lag",
                            "[SUSPECT] filler audio end -> agent audible",
                        ],
                    }
                ],
            )
        ],
        metadata={"source": "test", "query": 'accountId:"1"'},
    )

    rendered = window_latency_stats.render_markdown(payload)

    assert "## Suspect Metrics" in rendered
    assert "[SUSPECT] User speak end -> isFinal lag" in rendered
    assert "## Metric Summary" in rendered
    assert "User speak end -> Filler audible" in rendered
    assert "## Worst Turns" in rendered
    assert "Need help" in rendered
