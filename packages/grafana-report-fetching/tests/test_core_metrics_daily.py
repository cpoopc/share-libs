from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cptools_grafana_report_fetching.core_metrics_daily import (
    MetricSample,
    build_markdown_report,
    compute_time_range,
    summarize_rows,
)


def test_compute_time_range_for_explicit_day() -> None:
    time_from, time_to, label = compute_time_range("2026-03-15")

    assert time_from == "2026-03-15T00:00:00"
    assert time_to == "2026-03-16T00:00:00"
    assert label == "2026-03-15"


def test_summarize_rows_uses_requested_reducer() -> None:
    rows = [
        {"timestamp": "2026-03-15T00:00:00", "value": 2.0},
        {"timestamp": "2026-03-15T01:00:00", "value": 4.0},
        {"timestamp": "2026-03-15T02:00:00", "value": None},
        {"timestamp": "2026-03-15T03:00:00", "value": 8.0},
    ]

    assert summarize_rows(rows, "avg") == 14.0 / 3.0
    assert summarize_rows(rows, "max") == 8.0
    assert summarize_rows(rows, "min") == 2.0
    assert summarize_rows(rows, "last") == 8.0
    assert summarize_rows(rows, "sum") == 14.0
    assert summarize_rows(rows, "p75") == 6.0


def test_build_markdown_report_groups_by_service() -> None:
    samples = [
        MetricSample(
            service="assistant-runtime",
            key="TTFT P95 - Nova",
            title="TTFT P95 - Nova",
            description="P95 latency from generate request to first result.",
            value=1.23,
            unit="s",
            aggregation="max",
            promql="expr_a",
        ),
        MetricSample(
            service="agent-service",
            key="llm_error_ratio",
            title="LLM error ratio",
            description="Average request error ratio.",
            value=0.45,
            unit="%",
            aggregation="avg",
            promql="expr_b",
        ),
    ]

    report = build_markdown_report(
        samples=samples,
        day_label="2026-03-15",
        config_path=Path("core-metrics-daily.yaml"),
    )

    assert "# Core Metrics Daily Report" in report
    assert "## assistant-runtime" in report
    assert "## agent-service" in report
    assert "TTFT P95 - Nova" in report
    assert "llm_error_ratio" in report
