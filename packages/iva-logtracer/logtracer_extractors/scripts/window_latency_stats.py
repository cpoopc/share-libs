#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from logtracer_extractors.runtime import get_app_root, get_output_root
from logtracer_extractors.scripts import diagnostic_report

APP_ROOT = get_app_root()
OUTPUT_SESSION_ROOT = get_output_root()
DISCOVERY_INDEX = "*:*-logs-air_assistant_runtime-*"
TOP_WORST_TURNS = 5

if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from logtracer_extractors.kibana_client import KibanaClient, parse_time_range
from logtracer_extractors.iva.discovery.service import aggregate_sessions, fetch_all_hits
from logtracer_extractors.iva.session_tracer import (
    DEFAULT_CONVERSATION_LOADERS,
    DEFAULT_SESSION_LOADERS,
    SessionTraceOrchestrator,
    format_logs_plain,
    get_output_dir,
    save_ai_analysis_files,
)


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    row_field: str
    threshold_ms: float
    eligible_scope: str
    evidence: str = "derived/proxy"


METRIC_SPECS = (
    MetricSpec(
        key="user_speak_end_to_is_final_lag_ms",
        label="User speak end -> isFinal lag",
        row_field="stt_lag_ms",
        threshold_ms=800.0,
        eligible_scope="user_turn",
    ),
    MetricSpec(
        key="user_speak_end_to_filler_audible_ms",
        label="User speak end -> Filler audible",
        row_field="user_speak_end_to_filler_audible_ms",
        threshold_ms=2500.0,
        eligible_scope="filler_turn",
    ),
    MetricSpec(
        key="filler_audio_end_to_agent_audible_ms",
        label="Filler audio end -> Agent audible",
        row_field="filler_audio_end_to_agent_audible_ms",
        threshold_ms=800.0,
        eligible_scope="filler_turn",
    ),
)


def _fmt_ms(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.0f} ms"


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value) * 100:.1f}%"


def _shorten(value: Any, limit: int = 80) -> str:
    text = str(value or "N/A").strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)] + "..."


def _is_user_turn_type(turn_type: Any) -> bool:
    return str(turn_type or "").startswith("user_turn")


def _percentile(values_ms: list[float], percentile: float) -> float | None:
    if not values_ms:
        return None
    ordered = sorted(float(value) for value in values_ms)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (percentile / 100.0)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value and value not in seen:
            ordered.append(value)
            seen.add(value)
    return ordered


def _summarize_metric_series(
    *,
    metric: MetricSpec,
    values_ms: list[float],
    eligible_turn_count: int,
    total_user_turn_count: int,
) -> dict[str, Any]:
    count = len(values_ms)
    coverage_rate = (count / eligible_turn_count) if eligible_turn_count else None
    summary = {
        "key": metric.key,
        "label": metric.label,
        "evidence": metric.evidence,
        "threshold_ms": metric.threshold_ms,
        "count": count,
        "eligible_turn_count": eligible_turn_count,
        "total_user_turn_count": total_user_turn_count,
        "coverage_rate": coverage_rate,
        "avg_ms": (sum(values_ms) / count) if values_ms else None,
        "p50_ms": _percentile(values_ms, 50.0),
        "p75_ms": _percentile(values_ms, 75.0),
        "p90_ms": _percentile(values_ms, 90.0),
        "p95_ms": _percentile(values_ms, 95.0),
        "max_ms": max(values_ms) if values_ms else None,
        "markers": [],
    }

    markers: list[str] = []
    if summary["p95_ms"] is not None and float(summary["p95_ms"]) >= metric.threshold_ms:
        markers.append(f"[SUSPECT] p95 >= {metric.threshold_ms:.0f} ms")
    if summary["max_ms"] is not None and float(summary["max_ms"]) >= metric.threshold_ms:
        markers.append(f"[SUSPECT] max >= {metric.threshold_ms:.0f} ms")
    if coverage_rate is not None and coverage_rate < 0.8:
        markers.append("[SUSPECT] coverage < 80%")
    summary["markers"] = markers
    return summary


def _session_turns_for_metric(
    *,
    session: dict[str, Any],
    metric: MetricSpec,
) -> tuple[int, list[dict[str, Any]], list[dict[str, Any]]]:
    rows = session.get("turn_summary_matrix") or []
    filler_turn_numbers = {
        turn.get("turn_number")
        for turn in (session.get("manual_rca_view") or {}).get("filler_turns") or []
        if isinstance(turn.get("turn_number"), int)
    }

    user_rows = [row for row in rows if _is_user_turn_type(row.get("turn_type"))]
    eligible_rows: list[dict[str, Any]] = []
    for row in user_rows:
        if metric.eligible_scope == "user_turn":
            eligible_rows.append(row)
            continue
        if row.get("turn_number") in filler_turn_numbers:
            eligible_rows.append(row)
    return len(user_rows), eligible_rows, rows


def aggregate_latency_window_stats(
    *,
    session_diagnostics: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metric_values: dict[str, list[float]] = {metric.key: [] for metric in METRIC_SPECS}
    metric_eligible_counts: dict[str, int] = {metric.key: 0 for metric in METRIC_SPECS}
    worst_turns: dict[str, list[dict[str, Any]]] = {metric.key: [] for metric in METRIC_SPECS}

    user_turn_count = 0
    filler_turn_count = 0

    for session in session_diagnostics:
        session_id = session.get("session_id") or "unknown"
        conversation_id = session.get("conversation_id") or "unknown"
        session_dir = session.get("session_dir")
        filler_turn_numbers = {
            turn.get("turn_number")
            for turn in (session.get("manual_rca_view") or {}).get("filler_turns") or []
            if isinstance(turn.get("turn_number"), int)
        }
        filler_turn_count += len(filler_turn_numbers)

        for metric in METRIC_SPECS:
            current_user_turn_count, eligible_rows, _ = _session_turns_for_metric(session=session, metric=metric)
            if metric.key == METRIC_SPECS[0].key:
                user_turn_count += current_user_turn_count
            metric_eligible_counts[metric.key] += len(eligible_rows)

            for row in eligible_rows:
                value = row.get(metric.row_field)
                if value is None:
                    continue
                numeric_value = float(value)
                metric_values[metric.key].append(numeric_value)
                worst_turns[metric.key].append(
                    {
                        "session_id": session_id,
                        "conversation_id": conversation_id,
                        "session_dir": session_dir,
                        "turn_number": row.get("turn_number"),
                        "turn_type": row.get("turn_type"),
                        "transcript": row.get("transcript") or "N/A",
                        "ai_response": row.get("ai_response") or "N/A",
                        "value_ms": numeric_value,
                        "markers": row.get("markers") or [],
                    }
                )

    metric_payload = {
        metric.key: _summarize_metric_series(
            metric=metric,
            values_ms=metric_values[metric.key],
            eligible_turn_count=metric_eligible_counts[metric.key],
            total_user_turn_count=user_turn_count,
        )
        for metric in METRIC_SPECS
    }
    worst_turn_payload = {
        metric.key: sorted(
            worst_turns[metric.key],
            key=lambda item: item.get("value_ms") or -1,
            reverse=True,
        )[:TOP_WORST_TURNS]
        for metric in METRIC_SPECS
    }

    suspect_metrics = _ordered_unique(
        f"[SUSPECT] {metric.label}: {'; '.join(metric_payload[metric.key]['markers'])}"
        for metric in METRIC_SPECS
        if metric_payload[metric.key]["markers"]
    )

    return {
        "metadata": metadata or {},
        "session_count": len(session_diagnostics),
        "user_turn_count": user_turn_count,
        "filler_turn_count": filler_turn_count,
        "metrics": metric_payload,
        "suspect_metrics": suspect_metrics,
        "worst_turns": worst_turn_payload,
    }


def _append_markdown_table(lines: list[str], headers: list[str], rows: list[list[str]]) -> None:
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")


def render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = ["# Window Latency Stats", ""]
    metadata = payload.get("metadata") or {}

    lines.append("## Scope")
    lines.append(f"- Source: {metadata.get('source') or 'unknown'}")
    if metadata.get("query"):
        lines.append(f"- Query: `{metadata['query']}`")
    if metadata.get("start_time") or metadata.get("end_time"):
        lines.append(f"- Window: `{metadata.get('start_time') or 'N/A'}` -> `{metadata.get('end_time') or 'N/A'}`")
    if metadata.get("discovered_session_count") is not None:
        lines.append(f"- Discovered sessions: `{metadata['discovered_session_count']}`")
    if metadata.get("traced_session_count") is not None or metadata.get("reused_session_count") is not None:
        lines.append(
            f"- Trace inputs: reused=`{metadata.get('reused_session_count') or 0}`, "
            f"traced=`{metadata.get('traced_session_count') or 0}`, skipped=`{metadata.get('skipped_session_count') or 0}`"
        )
    lines.append(
        f"- Coverage base: user_turns=`{payload.get('user_turn_count') or 0}`, "
        f"filler_turns=`{payload.get('filler_turn_count') or 0}`"
    )
    lines.append("- Evidence: `user speak end` and `agent audible` are derived/proxy timestamps, not PBX hard truth.")

    suspect_metrics = payload.get("suspect_metrics") or []
    if suspect_metrics:
        lines.append("")
        lines.append("## Suspect Metrics")
        for marker in suspect_metrics:
            lines.append(f"- {marker}")

    lines.append("")
    lines.append("## Metric Summary")
    metric_rows: list[list[str]] = []
    for metric in METRIC_SPECS:
        item = (payload.get("metrics") or {}).get(metric.key) or {}
        metric_rows.append(
            [
                metric.label,
                str(item.get("count") or 0),
                str(item.get("eligible_turn_count") or 0),
                _fmt_pct(item.get("coverage_rate")),
                _fmt_ms(item.get("avg_ms")),
                _fmt_ms(item.get("p50_ms")),
                _fmt_ms(item.get("p75_ms")),
                _fmt_ms(item.get("p90_ms")),
                _fmt_ms(item.get("p95_ms")),
                _fmt_ms(item.get("max_ms")),
                "<br>".join(item.get("markers") or []) or "OK",
            ]
        )
    _append_markdown_table(
        lines,
        headers=["Metric", "Samples", "Eligible", "Coverage", "Avg", "P50", "P75", "P90", "P95", "Max", "Markers"],
        rows=metric_rows,
    )

    lines.append("")
    lines.append("## Worst Turns")
    for metric in METRIC_SPECS:
        lines.append("")
        lines.append(f"### {metric.label}")
        worst_turns = (payload.get("worst_turns") or {}).get(metric.key) or []
        if not worst_turns:
            lines.append("- No samples.")
            continue
        _append_markdown_table(
            lines,
            headers=["Session", "Turn", "Transcript", "AI Response", "Value", "Markers"],
            rows=[
                [
                    f"`{_shorten(turn.get('session_id'), 24)}`",
                    str(turn.get("turn_number") or "N/A"),
                    _shorten(turn.get("transcript"), 60),
                    _shorten(turn.get("ai_response"), 80),
                    _fmt_ms(turn.get("value_ms")),
                    "<br>".join(turn.get("markers") or []) or "OK",
                ]
                for turn in worst_turns
            ],
        )

    return "\n".join(lines).rstrip() + "\n"


def _sanitize_identifier(value: str) -> str:
    return value.replace("/", "_").replace("\\", "_")


def _find_existing_session_dir(*, session_id: str | None, conversation_id: str | None) -> Path | None:
    if not OUTPUT_SESSION_ROOT.exists():
        return None

    patterns: list[str] = []
    if session_id and conversation_id:
        patterns.append(f"*_{_sanitize_identifier(session_id)}-{_sanitize_identifier(conversation_id)}")
        patterns.append(f"{_sanitize_identifier(session_id)}-{_sanitize_identifier(conversation_id)}")
    if session_id:
        patterns.append(f"*_{_sanitize_identifier(session_id)}-*")
        patterns.append(f"{_sanitize_identifier(session_id)}-*")
    if conversation_id:
        patterns.append(f"*_*-{_sanitize_identifier(conversation_id)}")
        patterns.append(f"unknown-{_sanitize_identifier(conversation_id)}")

    candidates: list[Path] = []
    for pattern in _ordered_unique(patterns):
        candidates.extend(OUTPUT_SESSION_ROOT.glob(pattern))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)[0]


def _save_trace_context(ctx: Any, result: dict[str, Any], *, save_json: bool) -> Path:
    session_id = ctx.session_id or "unknown"
    conversation_id = ctx.conversation_id
    if not conversation_id:
        raise RuntimeError(f"Trace for {session_id} did not produce a conversationId")

    output_dir = get_output_dir(session_id, conversation_id)
    logs = result.get("logs", {})
    for component, component_logs in logs.items():
        if not component_logs:
            continue
        if save_json:
            json_path = output_dir / f"{component}_trace.json"
            json_path.write_text(
                json.dumps(component_logs, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )

        log_path = output_dir / f"{component}_message.log"
        lines = [
            f"[{log.get('@timestamp', '')}] {log.get('message', '')}"
            for log in sorted(component_logs, key=lambda item: item.get("@timestamp", ""))
        ]
        log_path.write_text("\n".join(lines), encoding="utf-8")

    combine_path = output_dir / "combine.log"
    combine_path.write_text(format_logs_plain(logs), encoding="utf-8")

    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "session_id": ctx.session_id,
                "conversation_id": ctx.conversation_id,
                "srs_session_id": ctx.srs_session_id,
                "sgs_session_id": ctx.sgs_session_id,
                "summary": ctx.get_summary(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    save_ai_analysis_files(output_dir, logs, json.loads(summary_path.read_text(encoding="utf-8")))
    return output_dir


def _trace_session_candidate(
    *,
    client: KibanaClient,
    candidate: Any,
    trace_last: str,
    trace_size: int,
    session_key: str,
    save_json: bool,
) -> Path:
    orchestrator = SessionTraceOrchestrator(client)
    enabled_loaders = set(DEFAULT_SESSION_LOADERS)

    if session_key == "conversationId":
        conversation_id = candidate.session_id
        ctx = orchestrator.trace_by_conversation(
            conversation_id=conversation_id,
            time_range=trace_last,
            enabled_loaders=set(DEFAULT_CONVERSATION_LOADERS),
            size=trace_size,
        )
    else:
        ctx = orchestrator.trace_by_session(
            session_id=candidate.session_id,
            time_range=trace_last,
            enabled_loaders=enabled_loaders,
            size=trace_size,
        )

    return _save_trace_context(ctx, ctx.to_result(), save_json=save_json)


def _resolve_time_range(args: argparse.Namespace) -> tuple[str | None, str | None]:
    if args.last:
        return parse_time_range(args.last), "now"
    return args.start, args.end


def _resolve_query(args: argparse.Namespace) -> tuple[str, str | None]:
    if args.query:
        return args.query, args.field
    if args.account_id:
        return f'accountId:"{args.account_id}"', "accountId"
    if args.field and args.value:
        return f'{args.field}:"{args.value}"', args.field
    raise ValueError("Provide either --query, --account-id, or --field/--value.")


def _discover_session_candidates(args: argparse.Namespace) -> tuple[list[Any], dict[str, Any]]:
    client = KibanaClient.from_env()
    start_time, end_time = _resolve_time_range(args)
    query, matched_field = _resolve_query(args)
    paged_hits = fetch_all_hits(
        client=client,
        query=query,
        index=args.index,
        start_time=start_time,
        end_time=end_time,
        page_size=args.page_size,
        max_pages=args.max_pages,
    )
    sessions = aggregate_sessions(
        hits=paged_hits.hits,
        session_key=args.session_key,
        matched_field_name=matched_field,
    )
    sessions = sorted(sessions, key=lambda session: session.first_timestamp, reverse=True)
    limited_sessions = sessions[: args.max_sessions]
    metadata = {
        "source": "online time window",
        "query": query,
        "start_time": start_time,
        "end_time": end_time,
        "discovered_session_count": len(sessions),
        "discovery_stats": {
            "total_hits": paged_hits.total_hits,
            "fetched_hits": len(paged_hits.hits),
            "page_count": paged_hits.page_count,
            "page_size": args.page_size,
            "max_pages": args.max_pages,
        },
        "candidate_session_count": len(limited_sessions),
    }
    return limited_sessions, metadata


def _session_dirs_from_candidates(args: argparse.Namespace, candidates: list[Any]) -> tuple[list[Path], dict[str, int]]:
    client = KibanaClient.from_env()
    reused = 0
    traced = 0
    skipped = 0
    session_dirs: list[Path] = []

    for candidate in candidates:
        conversation_id = getattr(candidate, "conversation_id", None)
        existing = _find_existing_session_dir(session_id=candidate.session_id, conversation_id=conversation_id)
        if existing is not None:
            reused += 1
            session_dirs.append(existing)
            continue

        if args.no_trace:
            skipped += 1
            continue

        traced_dir = _trace_session_candidate(
            client=client,
            candidate=candidate,
            trace_last=args.trace_last,
            trace_size=args.trace_size,
            session_key=args.session_key,
            save_json=args.save_json,
        )
        traced += 1
        session_dirs.append(traced_dir)

    return session_dirs, {
        "reused_session_count": reused,
        "traced_session_count": traced,
        "skipped_session_count": skipped,
    }


def _load_session_diagnostics(
    *,
    session_dirs: list[Path],
    reported_symptom: str | None,
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for session_dir in session_dirs:
        session = diagnostic_report._build_session_diagnostic(session_dir, reported_symptom=reported_symptom)
        session["session_dir"] = str(session_dir)
        diagnostics.append(session)
    return diagnostics


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    metadata: dict[str, Any]
    session_dirs: list[Path]

    if args.session_dirs:
        session_dirs = [Path(session_dir) for session_dir in args.session_dirs]
        metadata = {
            "source": "saved session directories",
            "provided_session_count": len(session_dirs),
        }
    else:
        candidates, metadata = _discover_session_candidates(args)
        session_dirs, trace_metadata = _session_dirs_from_candidates(args, candidates)
        metadata.update(trace_metadata)

    diagnostics = _load_session_diagnostics(
        session_dirs=session_dirs,
        reported_symptom=args.reported_symptom,
    )
    metadata["analyzed_session_count"] = len(diagnostics)
    metadata["analyzed_session_dirs"] = [str(item) for item in session_dirs]
    return aggregate_latency_window_stats(session_diagnostics=diagnostics, metadata=metadata)


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.session_dirs:
        return
    if args.last and (args.start or args.end):
        parser.error("Use either --last or --start/--end, not both.")
    if not args.last and not (args.start and args.end):
        parser.error("Discovery mode requires --last or --start/--end.")
    if args.query and (args.field or args.value or args.account_id):
        parser.error("Use either --query, --account-id, or --field/--value.")
    if bool(args.field) ^ bool(args.value):
        parser.error("--field and --value must be provided together.")
    if not (args.query or args.account_id or (args.field and args.value)):
        parser.error("Discovery mode requires --query, --account-id, or --field/--value.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate production time-window latency stats for IVA/Nova user turns."
    )
    parser.add_argument("session_dirs", nargs="*", help="Saved iva session directories to aggregate directly")
    parser.add_argument("--query", help="Lucene/KQL query to discover candidate sessions")
    parser.add_argument("--account-id", help="Shortcut for accountId:\"...\"")
    parser.add_argument("--field", help="Assistant runtime field name for discovery")
    parser.add_argument("--value", help="Field value for discovery")
    parser.add_argument("--index", default=DISCOVERY_INDEX, help="Discovery index pattern")
    parser.add_argument("--session-key", default="sessionId", help="Discovery grouping key")
    parser.add_argument("--last", help="Relative time range, e.g. 24h")
    parser.add_argument("--start", help="Start time (ISO)")
    parser.add_argument("--end", help="End time (ISO)")
    parser.add_argument("--page-size", type=int, default=500, help="Discovery page size")
    parser.add_argument("--max-pages", type=int, default=20, help="Max discovery pages")
    parser.add_argument("--max-sessions", type=int, default=20, help="Max candidate sessions to analyze")
    parser.add_argument("--no-trace", action="store_true", help="Do not trace missing session dirs")
    parser.add_argument("--trace-last", default="24h", help="Time range used when tracing missing sessions")
    parser.add_argument("--trace-size", type=int, default=5000, help="Max logs per component during trace")
    parser.add_argument("--save-json", action="store_true", help="Also save raw trace JSON when tracing")
    parser.add_argument("--reported-symptom", help="Optional symptom forwarded into per-session diagnostics")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--output", "-o", help="Write report to file instead of stdout")
    args = parser.parse_args(argv)

    _validate_args(parser, args)
    payload = build_payload(args)
    output = json.dumps(payload, indent=2, ensure_ascii=False) if args.format == "json" else render_markdown(payload)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
        print(f"✅ Report saved to: {output_path}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
