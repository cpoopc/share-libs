#!/usr/bin/env python3
"""Summarize generic client/server tool calls from one or more traced IVA sessions."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple

from logtracer_extractors.iva.turn.analyzer import VoiceCallAnalyzer  # noqa: E402
from logtracer_extractors.iva.turn.models import parse_timestamp  # noqa: E402


DENIAL_PATTERNS = (
    "don't have any information",
    "do not have any information",
    "don't have information",
    "do not have information",
    "couldn't find",
    "could not find",
    "can't find",
    "cannot find",
    "didn't find",
    "did not find",
    "don't see",
    "do not see",
    "unable to find",
    "not able to find",
    "no information",
)

FOUND_PATTERNS = (
    "i found",
    "i do see",
    "i see a",
    "i see an",
    "i located",
    "i found everth",
    "i found james",
)

TRANSFER_SUCCESS_PATTERNS = (
    "transferring you",
    "call will be transferred",
    "please hold on",
    "please stay with me a moment",
)

TRANSFER_FAILURE_PATTERNS = (
    "not able to transfer",
    "unable to transfer",
    "not able to complete the transfer",
    "not able to complete",
    "unable to complete the transfer",
    "unable to complete",
    "can't transfer",
    "cannot transfer",
)

CLIENT_TOOL_NAMES = {
    "transfer_call",
    "hangup_call",
    "air_sendSms",
    "air_sendAppointmentLink",
}

CLIENT_DESCRIPTION_HINTS = (
    "transfer call",
    "hang up",
    "send sms",
    "appointment link",
)

SERVER_NAME_PREFIXES = ("air_get", "air_search")

SERVER_DESCRIPTION_HINTS = (
    "knowledge base",
    "company employee list",
    "company directory",
    "company location",
    "working hours",
    "business hours",
    "returns the day",
    "query the company",
    "get company",
)


def _iso_to_datetime(value: str | None):
    if not value:
        return None
    return parse_timestamp(value)


def _truncate(value: Any, limit: int = 120) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _effective_status(statuses: Iterable[str]) -> str:
    normalized = {status for status in statuses if status}
    if "failed" in normalized:
        return "failed"
    if "success" in normalized:
        return "success"
    if normalized:
        return sorted(normalized)[0]
    return "unknown"


def _lifecycle(start_seen: bool, end_seen: bool) -> str:
    if start_seen and end_seen:
        return "invoked_and_completed"
    if start_seen:
        return "invoked_no_completion"
    if end_seen:
        return "completion_only"
    return "observed_without_phase"


def _normalize_text(value: str | None) -> str:
    return (value or "").lower().replace("’", "'").replace("‘", "'")


def _safe_json_loads(value: str | None) -> Any:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _extract_tool_catalog(assistant_runtime_logs: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    catalog: Dict[str, Dict[str, str]] = {}

    for record in assistant_runtime_logs:
        message = record.get("message", "")
        if "toolDefinitions" not in message:
            continue
        try:
            if message.startswith("AgentCompletionResponse: "):
                payload = json.loads(message.split("AgentCompletionResponse: ", 1)[1])
                tool_definitions = (
                    payload.get("payload", {})
                    .get("init", {})
                    .get("info", {})
                    .get("toolDefinitions", [])
                )
            elif message.startswith("Received init: "):
                payload = json.loads(message.split("Received init: ", 1)[1])
                tool_definitions = payload.get("info", {}).get("toolDefinitions", [])
            else:
                continue
        except json.JSONDecodeError:
            continue

        for tool_def in tool_definitions:
            if not isinstance(tool_def, dict):
                continue
            name = str(tool_def.get("name") or "").strip()
            description = str(tool_def.get("description") or "")
            inferred = _infer_tool_type_from_catalog(name, description)
            if inferred:
                catalog[name] = inferred
        if catalog:
            break

    return catalog


def _infer_tool_type_from_catalog(name: str, description: str) -> Dict[str, str] | None:
    normalized_name = name.strip()
    description_text = description.lower()

    if normalized_name in CLIENT_TOOL_NAMES:
        return {"tool_type": "client", "tool_type_source": "catalog", "tool_type_confidence": "medium"}

    if normalized_name.startswith(SERVER_NAME_PREFIXES):
        return {"tool_type": "server", "tool_type_source": "catalog", "tool_type_confidence": "medium"}

    if any(hint in description_text for hint in CLIENT_DESCRIPTION_HINTS):
        return {"tool_type": "client", "tool_type_source": "catalog", "tool_type_confidence": "medium"}

    if any(hint in description_text for hint in SERVER_DESCRIPTION_HINTS):
        return {"tool_type": "server", "tool_type_source": "catalog", "tool_type_confidence": "medium"}

    return None


def _analyze_tool_output(raw_output: str, status: str, tool_name: str) -> Dict[str, Any]:
    parsed = _safe_json_loads(raw_output)
    result_presence = "unknown"
    error_message = ""

    if isinstance(parsed, dict):
        if "error" in parsed and isinstance(parsed["error"], dict):
            error_message = str(parsed["error"].get("message") or "")
        elif "message" in parsed and status == "failed":
            error_message = str(parsed.get("message") or "")

        if "result" in parsed:
            result = parsed["result"]
            if isinstance(result, list):
                result_presence = "empty" if not result else "non_empty"
            elif isinstance(result, str):
                stripped = result.strip()
                if stripped in {"", "[]", "{}", "null", "None"}:
                    result_presence = "empty"
                else:
                    result_presence = "non_empty"
            elif result in (None, False):
                result_presence = "empty"
            else:
                result_presence = "non_empty"
        elif "success" in parsed:
            if parsed.get("success") is False:
                result_presence = "empty"
            elif parsed.get("success") is True and tool_name == "transfer_call":
                result_presence = "non_empty"

    return {
        "result_presence": result_presence,
        "error_message": error_message,
    }


def _detect_turn_contradictions(ai_response: str, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    ai_text = _normalize_text(ai_response)

    for call in tool_calls:
        tool_name = call.get("tool_name") or "(unknown)"
        status = call.get("status") or "unknown"
        result_presence = call.get("result_presence") or "unknown"
        error_message = call.get("error_message") or ""

        if status == "success" and result_presence == "non_empty":
            if any(pattern in ai_text for pattern in DENIAL_PATTERNS):
                findings.append(
                    {
                        "type": "answer_denies_successful_tool_result",
                        "tool_name": tool_name,
                        "severity": "error",
                        "message": "Tool returned a successful non-empty result, but the final answer denies having the information or finding the target.",
                    }
                )

        if status == "success" and result_presence == "empty":
            if any(pattern in ai_text for pattern in FOUND_PATTERNS):
                findings.append(
                    {
                        "type": "answer_claims_found_despite_empty_tool_result",
                        "tool_name": tool_name,
                        "severity": "error",
                        "message": "Tool returned an empty result, but the final answer claims the target was found.",
                    }
                )

        if tool_name == "transfer_call":
            has_transfer_success = any(pattern in ai_text for pattern in TRANSFER_SUCCESS_PATTERNS)
            has_transfer_failure = any(pattern in ai_text for pattern in TRANSFER_FAILURE_PATTERNS)

            if status == "success" and has_transfer_failure:
                findings.append(
                    {
                        "type": "answer_claims_transfer_failed_but_tool_succeeded",
                        "tool_name": tool_name,
                        "severity": "error",
                        "message": "Transfer tool succeeded, but the final answer says the transfer could not be completed.",
                    }
                )

            if status == "failed" and has_transfer_success and not has_transfer_failure:
                findings.append(
                    {
                        "type": "answer_claims_transfer_success_but_tool_failed",
                        "tool_name": tool_name,
                        "severity": "error",
                        "message": "Transfer tool failed, but the final answer only claims the transfer is happening.",
                    }
                )

            if status == "failed" and has_transfer_success and has_transfer_failure:
                findings.append(
                    {
                        "type": "mixed_transfer_outcome_messaging",
                        "tool_name": tool_name,
                        "severity": "warning",
                        "message": "Transfer tool failed, and the final answer contains both transfer-success and transfer-failure language.",
                        "error_message": error_message,
                    }
                )

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for finding in findings:
        key = (finding["type"], finding["tool_name"], finding["message"])
        if key not in seen:
            seen.add(key)
            deduped.append(finding)
    return deduped


def _group_tool_calls(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: List[Dict[str, Any]] = []

    for call in tool_calls:
        tool_name = call.get("tool_name") or "(unknown)"
        tool_type = call.get("tool_type") or "unknown"
        tool_call_id = call.get("tool_call_id") or ""

        existing = None
        call_ts = _iso_to_datetime(call.get("start_timestamp") or call.get("end_timestamp"))
        for candidate in grouped:
            same_name = candidate["tool_name"] == tool_name
            same_id = bool(tool_call_id) and candidate.get("tool_call_id") == tool_call_id
            type_compatible = (
                candidate.get("tool_type") in {"unknown", tool_type}
                or tool_type in {"unknown", candidate.get("tool_type")}
            )
            candidate_ts = _iso_to_datetime(candidate.get("start_timestamp") or candidate.get("end_timestamp"))
            close_in_time = True
            if call_ts and candidate_ts:
                close_in_time = abs((call_ts - candidate_ts).total_seconds()) <= 3

            if same_id or (same_name and type_compatible and close_in_time):
                existing = candidate
                break

        if existing is None:
            existing = {
                "tool_name": tool_name,
                "tool_type": tool_type,
                "tool_type_source": "explicit" if tool_type != "unknown" else "unknown",
                "tool_type_confidence": "high" if tool_type != "unknown" else "low",
                "tool_call_id": tool_call_id,
                "observed_components": [],
                "start_timestamp": None,
                "end_timestamp": None,
                "input": "",
                "output": "",
                "statuses": [],
            }
            grouped.append(existing)

        component = call.get("source_component") or "unknown"
        if component not in existing["observed_components"]:
            existing["observed_components"].append(component)

        if not existing.get("tool_call_id") and tool_call_id:
            existing["tool_call_id"] = tool_call_id
        if existing.get("tool_type") == "unknown" and tool_type != "unknown":
            existing["tool_type"] = tool_type
            existing["tool_type_source"] = "explicit"
            existing["tool_type_confidence"] = "high"

        for field in ("input", "output"):
            if not existing[field] and call.get(field):
                existing[field] = call[field]

        status = call.get("status") or "unknown"
        if status not in existing["statuses"]:
            existing["statuses"].append(status)

        start_ts = call.get("start_timestamp")
        end_ts = call.get("end_timestamp")
        current_start = existing.get("start_timestamp")
        current_end = existing.get("end_timestamp")

        if start_ts:
            if not current_start:
                existing["start_timestamp"] = start_ts
            else:
                start_dt = _iso_to_datetime(start_ts)
                current_start_dt = _iso_to_datetime(current_start)
                if start_dt and current_start_dt and start_dt < current_start_dt:
                    existing["start_timestamp"] = start_ts

        if end_ts:
            if not current_end:
                existing["end_timestamp"] = end_ts
            else:
                end_dt = _iso_to_datetime(end_ts)
                current_end_dt = _iso_to_datetime(current_end)
                if end_dt and current_end_dt and end_dt > current_end_dt:
                    existing["end_timestamp"] = end_ts

    collapsed = []
    for item in grouped:
        item["observed_components"].sort()
        item["status"] = _effective_status(item.pop("statuses", []))
        item["lifecycle"] = _lifecycle(
            item.get("start_timestamp") is not None,
            item.get("end_timestamp") is not None,
        )
        output_analysis = _analyze_tool_output(item.get("output", ""), item["status"], item["tool_name"])
        item.update(output_analysis)

        start_dt = _iso_to_datetime(item.get("start_timestamp"))
        end_dt = _iso_to_datetime(item.get("end_timestamp"))
        if start_dt and end_dt and end_dt >= start_dt:
            item["duration_ms"] = (end_dt - start_dt).total_seconds() * 1000.0
        else:
            item["duration_ms"] = None

        item["input_excerpt"] = _truncate(item.pop("input", ""))
        item["output_excerpt"] = _truncate(item.pop("output", ""))
        collapsed.append(item)

    collapsed.sort(
        key=lambda item: (
            item.get("start_timestamp") or item.get("end_timestamp") or "",
            item.get("tool_type") or "",
            item.get("tool_name") or "",
        )
    )
    return collapsed


def _apply_catalog_fallback(tool_calls: List[Dict[str, Any]], tool_catalog: Dict[str, Dict[str, str]]) -> None:
    for call in tool_calls:
        if call.get("tool_type") != "unknown":
            continue
        inferred = tool_catalog.get(call.get("tool_name") or "")
        if not inferred:
            continue
        call.update(inferred)


def summarize_session(session_dir: Path) -> Dict[str, Any]:
    if not any(session_dir.glob("*_trace.json")):
        raise SystemExit(
            f"No *_trace.json files found in {session_dir}. "
            "Rerun run_trace.sh with --save-json before running toolcall_audit.py."
        )

    analyzer = VoiceCallAnalyzer(session_dir)
    report = analyzer.analyze()
    tool_catalog = _extract_tool_catalog(analyzer.logs.get("assistant_runtime", []))

    summary: Dict[str, Any] = {
        "session_dir": str(session_dir),
        "session_id": report.session_id,
        "conversation_id": report.conversation_id,
        "total_turns": report.total_turns,
        "tool_call_count": 0,
        "turns_with_tools": 0,
        "tool_catalog": tool_catalog,
        "turns": [],
    }

    for turn in report.turns:
        grouped_calls = _group_tool_calls(turn.tool_calls)
        _apply_catalog_fallback(grouped_calls, tool_catalog)
        contradictions = _detect_turn_contradictions(turn.ai_response or "", grouped_calls)
        if grouped_calls:
            summary["turns_with_tools"] += 1
        summary["tool_call_count"] += len(grouped_calls)
        summary["turns"].append(
            {
                "turn_number": turn.turn_number,
                "turn_type": turn.turn_type,
                "start_timestamp": turn.start_timestamp,
                "end_timestamp": turn.end_timestamp,
                "duration_ms": turn.duration_ms,
                "ttft_ms": turn.ttft_ms,
                "latency_breakdown": turn.latency_breakdown,
                "user_transcript": _truncate(turn.user_transcript),
                "ai_response": _truncate(turn.ai_response),
                "tool_calls": grouped_calls,
                "anomalies": turn.anomalies,
                "contradictions": contradictions,
            }
        )

    return summary


def aggregate_sessions(sessions: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    by_tool_type: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    by_lifecycle: Counter[str] = Counter()
    by_component: Counter[str] = Counter()
    by_tool_name: Counter[str] = Counter()
    by_contradiction_type: Counter[str] = Counter()
    by_tool_type_source: Counter[str] = Counter()

    for session in sessions:
        for turn in session["turns"]:
            for call in turn["tool_calls"]:
                by_tool_type[call.get("tool_type") or "unknown"] += 1
                by_status[call.get("status") or "unknown"] += 1
                by_lifecycle[call.get("lifecycle") or "observed_without_phase"] += 1
                by_tool_name[call.get("tool_name") or "(unknown)"] += 1
                by_tool_type_source[call.get("tool_type_source") or "unknown"] += 1
                for component in call.get("observed_components", []):
                    by_component[component] += 1
            for contradiction in turn.get("contradictions", []):
                by_contradiction_type[contradiction.get("type") or "unknown"] += 1

    return {
        "by_tool_type": dict(by_tool_type),
        "by_status": dict(by_status),
        "by_lifecycle": dict(by_lifecycle),
        "by_component": dict(by_component),
        "by_tool_name": dict(by_tool_name.most_common(20)),
        "by_contradiction_type": dict(by_contradiction_type),
        "by_tool_type_source": dict(by_tool_type_source),
    }


def render_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# Tool Call Audit",
        "",
        f"- Sessions: {payload['session_count']}",
        f"- Tool calls: {payload['tool_call_count']}",
        "",
        "## Aggregate",
        "",
    ]

    for title, values in (
        ("By Tool Type", payload["aggregate"]["by_tool_type"]),
        ("By Status", payload["aggregate"]["by_status"]),
        ("By Lifecycle", payload["aggregate"]["by_lifecycle"]),
        ("By Component", payload["aggregate"]["by_component"]),
        ("By Tool Type Source", payload["aggregate"]["by_tool_type_source"]),
        ("By Contradiction Type", payload["aggregate"]["by_contradiction_type"]),
    ):
        lines.append(f"### {title}")
        if not values:
            lines.append("- None")
        else:
            for key, value in values.items():
                lines.append(f"- `{key}`: {value}")
        lines.append("")

    lines.append("## Session Details")
    for session in payload["sessions"]:
        lines.append("")
        lines.append(f"### `{session['session_id'] or 'unknown-session'}`")
        lines.append(f"- Conversation: `{session['conversation_id'] or 'N/A'}`")
        lines.append(f"- Turns: {session['total_turns']}")
        lines.append(f"- Turns with tools: {session['turns_with_tools']}")
        lines.append(f"- Tool calls: {session['tool_call_count']}")
        lines.append(f"- Directory: `{session['session_dir']}`")
        for turn in session["turns"]:
            if not turn["tool_calls"]:
                continue
            lines.append("")
            lines.append(f"#### Turn {turn['turn_number']} ({turn['turn_type']})")
            lines.append(f"- Duration: {turn.get('duration_ms', 0):.0f} ms")
            if turn.get("ttft_ms") is not None:
                lines.append(f"- TTFT: {turn['ttft_ms']:.0f} ms")
            breakdown = turn.get("latency_breakdown") or {}
            if breakdown:
                llm_total = breakdown.get("llm_total_ms")
                non_llm = breakdown.get("non_llm_ms")
                if llm_total is not None or non_llm is not None:
                    lines.append(
                        f"- Latency breakdown: llm_total={llm_total or 0:.0f} ms, "
                        f"non_llm={non_llm or 0:.0f} ms"
                    )
            if turn["user_transcript"]:
                lines.append(f"- User: {turn['user_transcript']}")
            if turn["ai_response"]:
                lines.append(f"- AI: {turn['ai_response']}")
            for call in turn["tool_calls"]:
                duration = f"{call['duration_ms']:.0f} ms" if call.get("duration_ms") is not None else "N/A"
                components = ", ".join(call["observed_components"]) or "unknown"
                lines.append(
                    f"- `{call['tool_type']}` `{call['tool_name']}`: "
                    f"status={call['status']}, lifecycle={call['lifecycle']}, "
                    f"components={components}, duration={duration}, "
                    f"type_source={call.get('tool_type_source', 'unknown')}, "
                    f"confidence={call.get('tool_type_confidence', 'low')}"
                )
                if call.get("input_excerpt"):
                    lines.append(f"- input: {call['input_excerpt']}")
                if call.get("output_excerpt"):
                    lines.append(f"- output: {call['output_excerpt']}")
            if turn.get("contradictions"):
                lines.append("- contradictions:")
                for contradiction in turn["contradictions"]:
                    lines.append(
                        f"- [{contradiction['severity']}] {contradiction['type']}: {contradiction['message']}"
                    )

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit generic client/server tool calls from traced IVA sessions.")
    parser.add_argument("session_dirs", nargs="+", help="Saved iva session output directories")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--output", "-o", help="Write audit output to a file")
    args = parser.parse_args()

    sessions = [summarize_session(Path(session_dir)) for session_dir in args.session_dirs]
    payload = {
        "session_count": len(sessions),
        "tool_call_count": sum(session["tool_call_count"] for session in sessions),
        "aggregate": aggregate_sessions(sessions),
        "sessions": sessions,
    }

    if args.format == "json":
        output = json.dumps(payload, indent=2, ensure_ascii=False)
    else:
        output = render_markdown(payload)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
        print(f"✅ Audit saved to: {output_path}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
