"""
Daily core metrics fetcher for IVA services.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
import json
import math
from pathlib import Path
from typing import Any, Iterable

import yaml

from .grafana_utils import get_grafana_client
from .runtime import get_output_root, resolve_core_metrics_config


@dataclass
class MetricSample:
    service: str
    key: str
    title: str
    description: str
    value: float | None
    unit: str
    aggregation: str
    promql: str


def load_metrics_config(config_path: str | Path) -> dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def compute_time_range(day: str | None = None) -> tuple[str, str, str]:
    if day:
        target_day = datetime.strptime(day, "%Y-%m-%d").date()
    else:
        target_day = date.today() - timedelta(days=1)

    next_day = target_day + timedelta(days=1)
    return (
        f"{target_day.isoformat()}T00:00:00",
        f"{next_day.isoformat()}T00:00:00",
        target_day.isoformat(),
    )


def summarize_rows(rows: Iterable[dict[str, Any]], aggregation: str) -> float | None:
    values = [row.get("value") for row in rows if row.get("value") is not None]
    if not values:
        return None

    if aggregation == "avg":
        return sum(values) / len(values)
    if aggregation == "max":
        return max(values)
    if aggregation == "min":
        return min(values)
    if aggregation == "sum":
        return sum(values)
    if aggregation == "last":
        return values[-1]
    if aggregation in {"p75", "p90", "p95"}:
        return compute_percentile(values, int(aggregation[1:]) / 100.0)

    raise ValueError(f"Unsupported aggregation: {aggregation}")


def compute_percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * quantile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)

    if lower_index == upper_index:
        return ordered[lower_index]

    lower_value = ordered[lower_index]
    upper_value = ordered[upper_index]
    weight = position - lower_index
    return lower_value + (upper_value - lower_value) * weight


def fetch_metric_samples(
    config: dict[str, Any],
    time_from: str,
    time_to: str,
) -> list[MetricSample]:
    samples: list[MetricSample] = []
    grafana_sources = config.get("grafana_sources", {})

    for metric in config.get("metrics", []):
        source_key = metric["source"]
        source_config = grafana_sources[source_key]
        client = get_grafana_client(source_config)
        rows = client.query_custom(
            expr=metric["promql"],
            time_from=time_from,
            time_to=time_to,
            datasource_uid=metric.get("datasource_uid", "prometheus"),
        )
        value = summarize_rows(rows, metric.get("aggregation", "avg"))
        samples.append(
            MetricSample(
                service=metric["service"],
                key=metric["key"],
                title=metric["title"],
                description=metric["description"],
                value=value,
                unit=metric.get("unit", ""),
                aggregation=metric.get("aggregation", "avg"),
                promql=metric["promql"],
            )
        )

    return samples


def format_metric_value(value: float | None, unit: str) -> str:
    if value is None:
        return "N/A"
    if unit == "%":
        return f"{value:.2f}%"
    if unit == "s":
        return f"{value:.2f}s"
    if unit == "ms":
        return f"{value:.0f}ms"
    return f"{value:.2f}"


def build_markdown_report(
    samples: list[MetricSample],
    day_label: str,
    config_path: Path,
) -> str:
    lines = [
        "# Core Metrics Daily Report",
        "",
        f"**Date**: {day_label}",
        f"**Config**: `{config_path}`",
        f"**Generated**: {datetime.now().isoformat(timespec='seconds')}",
        "",
    ]

    services = sorted({sample.service for sample in samples})
    for service in services:
        service_samples = [sample for sample in samples if sample.service == service]
        lines.append(f"## {service}")
        lines.append("")
        lines.append("| Key | Metric | Value | Aggregation |")
        lines.append("| --- | --- | --- | --- |")
        for sample in service_samples:
            lines.append(
                f"| {sample.key} | {sample.title} | {format_metric_value(sample.value, sample.unit)} | {sample.aggregation} |"
            )
        lines.append("")

    return "\n".join(lines)


def build_json_report(samples: list[MetricSample], day_label: str) -> dict[str, Any]:
    return {
        "date": day_label,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "metrics": [asdict(sample) for sample in samples],
    }


def run_core_metrics_daily(args) -> int:
    config_path = Path(args.config).expanduser() if args.config else resolve_core_metrics_config()
    config = load_metrics_config(config_path)
    time_from, time_to, day_label = compute_time_range(args.day)
    samples = fetch_metric_samples(config, time_from=time_from, time_to=time_to)

    output_dir = (
        Path(args.output_dir).expanduser()
        if args.output_dir
        else get_output_root() / "core-metrics-daily"
    ) / day_label
    output_dir.mkdir(parents=True, exist_ok=True)

    json_report = build_json_report(samples, day_label)
    markdown_report = build_markdown_report(samples, day_label, config_path)

    json_path = output_dir / "metrics.json"
    md_path = output_dir / "summary.md"
    json_path.write_text(json.dumps(json_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(markdown_report + "\n", encoding="utf-8")

    if args.stdout_format == "json":
        print(json.dumps(json_report, indent=2, ensure_ascii=False))
    else:
        print(markdown_report)
        print()
        print(f"JSON: {json_path}")
        print(f"Markdown: {md_path}")

    return 0
