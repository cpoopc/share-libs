#!/usr/bin/env python3
"""Generate a generic IVA diagnostic report with speech linkage and latency details."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Iterable, List


SCRIPT_DIR = Path(__file__).resolve().parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import toolcall_audit  # noqa: E402
from logtracer_extractors.iva.turn.models import parse_timestamp  # noqa: E402


LOG_TS_PATTERN = re.compile(r"^\[(?P<ts>[^\]]+)\]\s*(?P<body>.*)$")
SESSION_ID_FIELD_PATTERN = re.compile(r'session_id(?:=Path\(")?(?:=|: )"?([0-9a-f-]{36})', re.IGNORECASE)
REQUEST_SESSION_ID_PATTERN = re.compile(r"request_session_id=([0-9a-f-]{36})", re.IGNORECASE)
URL_SESSION_ID_PATTERN = re.compile(r"/v1/session/([0-9a-f-]{36})", re.IGNORECASE)
REQUEST_ID_PATTERN = re.compile(r"request_id=([0-9a-f-]+-\d+)", re.IGNORECASE)
SSEQ_PATTERN = re.compile(r"sseq:\s*(\d+)")
ASR_LATENCY_PATTERN = re.compile(r"asr_latency=([0-9.]+)")
IVA_DELIVERY_PATTERN = re.compile(r"iva_delivery_latency=([0-9.]+)")
TRANSCRIPT_RESULT_PATTERN = re.compile(
    r"Process transcript result is_final=(?P<is_final>true|false)\s+words=(?P<words>\d+)",
    re.IGNORECASE,
)
SGS_FIRST_CHUNK_PATTERN = re.compile(r"first chunk received latency=([0-9.]+)")
PLAYBACK_DURATION_PATTERN = re.compile(
    r"Received event: playback (?P<state>finished|interrupted) .*?duration_ms:\s*(?P<duration>\d+).*?sseq:\s*(?P<sseq>\d+)",
    re.IGNORECASE,
)
NEW_GENERATE_PATTERN = re.compile(
    r"new generate request request_session_id=(?P<request_session_id>[0-9a-f-]{36}) .*?req=Some\((?P<kind>Request|Cancel)",
    re.IGNORECASE,
)

SRS_CONNECT_MARKERS = (
    ("POST /v1/session/", "create_session"),
    ("Configuring meeting transcript", "configure_transcript"),
    ("Media negotiation succeeded", "media_negotiation_succeeded"),
    ("recognize stream established", "recognize_stream_established"),
    ("Connected successfully", "provider_connected"),
)

SRS_DISCONNECT_MARKERS = (
    ("Client disconnected, stopping IVA recognition", "client_disconnected", False),
    ("Audio stream ended, closing stream", "audio_stream_ended", False),
    ("Transcript channel closed", "transcript_channel_closed", True),
    ("channel closed", "channel_closed", True),
    ("Transcription error:", "transcription_error", True),
    ("drop:", "provider_drop", True),
    ("Stopping MeetingInfo", "stop_request", False),
    ("Media engine shutdown", "media_engine_shutdown", False),
    ("timed out", "timeout", True),
)

SGS_DISCONNECT_MARKERS = (
    ("client has dropped", "client_dropped", True),
    ("req=Some(Cancel(", "cancel_requested", False),
)

LATENCY_BUCKET_ORDER = (
    "User/PBX",
    "SRS/ASR",
    "assistant_runtime",
    "NCA orchestration",
    "GMG/LLM",
    "Tooling",
    "TTS/playback",
)

JSON_OBJECT_PATTERN = re.compile(r"(\{.*\})")
CREATE_NOVA_REQUEST_PATTERN = re.compile(
    r"Creating Nova conversation for accountId:\s*(?P<account_id>\d+), requestId:\s*(?P<request_id>[0-9a-f-]{36})",
    re.IGNORECASE,
)
START_CONVERSATION_OK_PATTERN = re.compile(
    r"POST .*?/ai/nova/v1/internal/start-conversation:\s*(?P<status>OK|Created|Success)",
    re.IGNORECASE,
)
NOVA_CONVERSATION_CREATED_PATTERN = re.compile(
    r"Nova conversation has been created:\s*(?P<conversation_id>[0-9a-f-]{36}), requestId:\s*(?P<request_id>[0-9a-f-]{36})",
    re.IGNORECASE,
)
SPEECH_RECOGNITION_STARTED_PATTERN = re.compile(r"Speech recognition started:\s*(\{.*\})")
SPEECH_GENERATION_STARTED_PATTERN = re.compile(r"Speech generation started:\s*(\{.*\})")
CALCULATED_FLAGS_PATTERN = re.compile(r"calculateFeatureFlags final feature flags:\s*(\{.*\})")
PARSED_FLAGS_PATTERN = re.compile(r"Parsed feature flags:\s*(\{.*\})")
ASSISTANT_CONFIG_FOUND_PATTERN = re.compile(r"Assistant config found, id:\s*([0-9a-f-]{36})", re.IGNORECASE)
EXTERNAL_LOOKUP_PATTERN = re.compile(
    r"ExternalAssistantLookupConfig\(rcAccountId=(?P<account_id>\d+), applicationId=(?P<application_id>[^,]+), "
    r"externalAssistantId=(?P<assistant_id>[0-9a-f-]{36}), assistantConfigurationProviderUrl=(?P<url>[^,]+), "
    r"rcExtensionId=(?P<extension_id>[^,]+), solution=(?P<solution>[^,]+), groupTag=(?P<group_tag>[^)]+)\)",
    re.IGNORECASE,
)
TOOL_RETRIEVED_PATTERN = re.compile(r"Retrieved tools:\s*configs=(\d+), schemas=(\d+), tools=(\d+)", re.IGNORECASE)
RAW_ENABLED_SKILLS_PATTERN = re.compile(r"Assistant raw enabled skills:\s*(\[[^\]]*\])", re.IGNORECASE)
GRAPH_SKILLS_PATTERN = re.compile(r"Sampling the graph for bundle:\s*([^,]+), skills:\s*(.+)$", re.IGNORECASE)
PBX_BUILDER_PATTERN = re.compile(
    r"Creating PBX Assistant Builder with solution=(?P<solution>[^,]+), modelGroupTag=(?P<group_tag>.+)$",
    re.IGNORECASE,
)
RECEIVED_INIT_PATTERN = re.compile(r"Received init:\s*(\{.*\})")
AGENT_INIT_PATTERN = re.compile(r'AgentCompletionResponse:\s*(\{.*"oneofKind":"init".*\})')
KAFKA_SUMMARY_PATTERN = re.compile(r"Produced to Kafka, msg:\s*(\{.*\})")
CONTEXT_FIELDS_PATTERN = re.compile(
    r"accountId\":(?P<account_id>\d+).*?assistantId\":\"(?P<assistant_id>[0-9a-f-]{36}).*?conversationId\":\"(?P<conversation_id>[0-9a-f-]{36})",
    re.IGNORECASE,
)
CONVERSATION_END_REQUEST_PATTERN = re.compile(
    r"Sending ConversationEndRequest for conversation (?P<conversation_id>[0-9a-f-]{36}), reason: (?P<reason>[A-Za-z_]+)",
    re.IGNORECASE,
)
PATCH_CONVERSATION_ENDED_PATTERN = re.compile(r"Patch conversation ended with reason: (?P<reason>[A-Za-z_]+)", re.IGNORECASE)
AR_GENERATION_REQUEST_PATTERN = re.compile(
    r"Sending generation request for sseq:\s*(?P<sseq>\d+),\s*isFinal:\s*(?P<is_final>true|false)",
    re.IGNORECASE,
)
AR_FILLER_TTFT_PATTERN = re.compile(r"Observed TTFT for type Filler:\s*(?P<ttft_ms>\d+)ms", re.IGNORECASE)
AR_SET_PENDING_PATTERN = re.compile(r"setPendingTranscript:\s*(?P<before>.+?)\s*->\s*(?P<after>.+)")
NCA_FILLER_RACE_PATTERN = re.compile(r"Filler wins, race:\s*(?P<duration_ms>\d+)\s*ms", re.IGNORECASE)
NCA_RESPONSE_START_PATTERN = re.compile(r"Recording ResponseStart for component:\s*(?P<component>[A-Za-z_]+)", re.IGNORECASE)
NCA_FILLER_GENERATION_COMPLETED_PATTERN = re.compile(r"\[FILLER\]\s+filler generation completed", re.IGNORECASE)


def _safe_load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_json_from_match(text: Any) -> Any:
    if not text:
        return None
    if isinstance(text, (dict, list)):
        return text
    if not isinstance(text, str):
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _shorten(text: str, limit: int = 160) -> str:
    compact = " ".join(text.strip().split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _line_parts(line: str) -> tuple[str | None, str]:
    match = LOG_TS_PATTERN.match(line)
    if not match:
        return None, line.rstrip()
    return match.group("ts"), match.group("body").rstrip()


def _extract_session_ids(line: str) -> List[str]:
    ids = []
    ids.extend(SESSION_ID_FIELD_PATTERN.findall(line))
    ids.extend(REQUEST_SESSION_ID_PATTERN.findall(line))
    ids.extend(URL_SESSION_ID_PATTERN.findall(line))
    deduped: List[str] = []
    seen = set()
    for session_id in ids:
        if session_id not in seen:
            seen.add(session_id)
            deduped.append(session_id)
    return deduped


def _pick_session_id(line: str, expected_session_id: str | None, observed_ids: Iterable[str]) -> str | None:
    if expected_session_id and expected_session_id in line:
        return expected_session_id
    observed = list(observed_ids)
    if observed:
        return observed[0]
    return expected_session_id


def _is_error_line(line: str) -> bool:
    lowered = line.lower()
    return " warn " in lowered or " error " in lowered or " failed" in lowered or "failure" in lowered or "drop:" in lowered


def _latency_stats(values_ms: List[float]) -> Dict[str, float | int | None]:
    if not values_ms:
        return {"count": 0, "avg_ms": None, "max_ms": None}
    return {
        "count": len(values_ms),
        "avg_ms": sum(values_ms) / len(values_ms),
        "max_ms": max(values_ms),
    }


def _parse_log_timestamp(timestamp: str | None) -> Any:
    if not timestamp:
        return None
    try:
        return parse_timestamp(timestamp)
    except Exception:
        return None


def _delta_ms(start_ts: str | None, end_ts: str | None) -> float | None:
    start_dt = _parse_log_timestamp(start_ts)
    end_dt = _parse_log_timestamp(end_ts)
    if start_dt is None or end_dt is None:
        return None
    return (end_dt - start_dt).total_seconds() * 1000.0


def _avg_numeric(values: Iterable[Any]) -> float | None:
    numeric_values = [float(value) for value in values if value is not None]
    if not numeric_values:
        return None
    return sum(numeric_values) / len(numeric_values)


def _later_timestamp(*timestamps: str | None) -> str | None:
    latest_ts: str | None = None
    latest_dt = None
    for timestamp in timestamps:
        current_dt = _parse_log_timestamp(timestamp)
        if current_dt is None:
            continue
        if latest_dt is None or current_dt > latest_dt:
            latest_ts = timestamp
            latest_dt = current_dt
    return latest_ts


def _extract_request_sseq(request_id: str | None) -> int | None:
    if not request_id or "-" not in request_id:
        return None
    suffix = request_id.rsplit("-", 1)[-1]
    if not suffix.isdigit():
        return None
    return int(suffix)


def _event_within_window(
    event_ts: str | None,
    *,
    start_ts: str | None = None,
    end_ts: str | None = None,
    max_gap_before_ms: float | None = None,
) -> bool:
    event_dt = _parse_log_timestamp(event_ts)
    if event_dt is None:
        return False
    if start_ts:
        start_dt = _parse_log_timestamp(start_ts)
        if start_dt is not None and event_dt < start_dt:
            return False
    if end_ts:
        end_dt = _parse_log_timestamp(end_ts)
        if end_dt is not None and event_dt > end_dt:
            return False
    if max_gap_before_ms is not None and start_ts:
        start_dt = _parse_log_timestamp(start_ts)
        if start_dt is not None and (start_dt - event_dt).total_seconds() * 1000.0 > max_gap_before_ms:
            return False
    return True


def _first_event_after(
    events: Iterable[Dict[str, Any]],
    *,
    start_ts: str | None,
    end_ts: str | None = None,
    predicate: Any = None,
) -> Dict[str, Any] | None:
    for event in events:
        if predicate and not predicate(event):
            continue
        if _event_within_window(event.get("timestamp"), start_ts=start_ts, end_ts=end_ts):
            return event
    return None


def _last_event_before(
    events: Iterable[Dict[str, Any]],
    *,
    anchor_ts: str | None,
    max_gap_ms: float | None = None,
    predicate: Any = None,
) -> Dict[str, Any] | None:
    if not anchor_ts:
        return None
    anchor_dt = _parse_log_timestamp(anchor_ts)
    if anchor_dt is None:
        return None

    selected: Dict[str, Any] | None = None
    selected_dt = None
    for event in events:
        if predicate and not predicate(event):
            continue
        event_ts = event.get("finalize_timestamp") or event.get("final_timestamp") or event.get("timestamp")
        event_dt = _parse_log_timestamp(event_ts)
        if event_dt is None or event_dt > anchor_dt:
            continue
        if max_gap_ms is not None and (anchor_dt - event_dt).total_seconds() * 1000.0 > max_gap_ms:
            continue
        if selected_dt is None or event_dt > selected_dt:
            selected = event
            selected_dt = event_dt
    return selected


def _detect_latency_path(
    *,
    start_conversation: Dict[str, Any],
    assistant_configuration: Dict[str, Any],
    component_coverage: Dict[str, Any],
) -> str:
    feature_flags = assistant_configuration.get("feature_flags") or {}
    counts = component_coverage.get("counts") or {}
    agent_type = str(feature_flags.get("agent_type") or "").strip().lower()

    if start_conversation.get("is_nova") or agent_type == "nova":
        return "nova"
    if counts.get("nca", 0) or counts.get("gmg", 0):
        return "nova"

    if agent_type == "iva":
        return "iva"
    if assistant_configuration.get("source") == "agent_service" and not start_conversation.get("is_nova"):
        return "iva"
    if counts.get("agent_service", 0) and not counts.get("nca", 0) and not counts.get("gmg", 0):
        return "iva"

    return "unknown"


def _append_latency_segment(
    segments: List[Dict[str, Any]],
    *,
    segment_name: str,
    bucket: str,
    path: str,
    owner: str,
    evidence_level: str,
    duration_ms: Any,
    source_ref: str,
    turn_number: int | None = None,
    start_ts: str | None = None,
    end_ts: str | None = None,
) -> None:
    if duration_ms is None:
        return
    numeric = float(duration_ms)
    if math.isnan(numeric):
        return
    segments.append(
        {
            "segment_name": segment_name,
            "bucket": bucket,
            "path": path,
            "owner": owner,
            "evidence_level": evidence_level,
            "duration_ms": numeric,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "turn_number": turn_number,
            "source_ref": source_ref,
        }
    )


def _build_latency_segments(
    *,
    latency_path: str,
    speech: Dict[str, Any],
    turns: List[Dict[str, Any]],
    component_coverage: Dict[str, Any],
) -> List[Dict[str, Any]]:
    del component_coverage  # Reserved for future path-specific expansion.

    segments: List[Dict[str, Any]] = []
    srs_latency = ((speech.get("srs") or {}).get("latency") or {})
    sgs_latency = ((speech.get("sgs") or {}).get("latency") or {})

    _append_latency_segment(
        segments,
        segment_name="srs.asr_compute",
        bucket="SRS/ASR",
        path=latency_path,
        owner="cprc_srs",
        evidence_level="observed",
        duration_ms=((srs_latency.get("asr_latency_ms") or {}).get("avg_ms")),
        source_ref="speech.srs.latency.asr_latency_ms.avg_ms",
    )
    _append_latency_segment(
        segments,
        segment_name="srs.delivery_to_runtime",
        bucket="SRS/ASR",
        path=latency_path,
        owner="cprc_srs",
        evidence_level="observed",
        duration_ms=((srs_latency.get("iva_delivery_latency_ms") or {}).get("avg_ms")),
        source_ref="speech.srs.latency.iva_delivery_latency_ms.avg_ms",
    )
    _append_latency_segment(
        segments,
        segment_name="sgs.first_chunk",
        bucket="TTS/playback",
        path=latency_path,
        owner="cprc_sgs",
        evidence_level="observed",
        duration_ms=((sgs_latency.get("ttfc_ms") or {}).get("avg_ms")),
        source_ref="speech.sgs.latency.ttfc_ms.avg_ms",
    )
    _append_latency_segment(
        segments,
        segment_name="sgs.playback",
        bucket="TTS/playback",
        path=latency_path,
        owner="cprc_sgs",
        evidence_level="observed",
        duration_ms=((sgs_latency.get("playback_duration_ms") or {}).get("avg_ms")),
        source_ref="speech.sgs.latency.playback_duration_ms.avg_ms",
    )

    for index, turn in enumerate(turns):
        turn_number = turn.get("turn_number")
        turn_start = turn.get("start_timestamp")
        turn_end = turn.get("end_timestamp")
        latency_breakdown = turn.get("latency_breakdown") or {}

        _append_latency_segment(
            segments,
            segment_name=f"llm.total_proxy.turn_{turn_number}",
            bucket="GMG/LLM",
            path=latency_path,
            owner="turn_summary",
            evidence_level="derived",
            duration_ms=latency_breakdown.get("llm_total_ms"),
            source_ref=f"turns[{index}].latency_breakdown.llm_total_ms",
            turn_number=turn_number,
            start_ts=turn_start,
            end_ts=turn_end,
        )

        tool_total_ms = sum(
            float(call.get("duration_ms"))
            for call in turn.get("tool_calls", [])
            if call.get("duration_ms") is not None
        )
        if tool_total_ms > 0:
            _append_latency_segment(
                segments,
                segment_name=f"tooling.total.turn_{turn_number}",
                bucket="Tooling",
                path=latency_path,
                owner="toolcall_audit",
                evidence_level="derived",
                duration_ms=tool_total_ms,
                source_ref=f"turns[{index}].tool_calls[*].duration_ms",
                turn_number=turn_number,
                start_ts=turn_start,
                end_ts=turn_end,
            )

    return segments


def _build_latency_buckets(segments: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    buckets = {name: {"duration_ms": None, "segment_count": 0} for name in LATENCY_BUCKET_ORDER}
    for bucket_name in LATENCY_BUCKET_ORDER:
        bucket_segments = [segment for segment in segments if segment.get("bucket") == bucket_name]
        if not bucket_segments:
            continue
        buckets[bucket_name] = {
            "duration_ms": sum(float(segment["duration_ms"]) for segment in bucket_segments),
            "segment_count": len(bucket_segments),
        }
    return buckets


def _build_manual_rca_view(
    *,
    speech: Dict[str, Any],
    assistant_runtime_latency: Dict[str, Any],
    nca_latency: Dict[str, Any],
    turns: List[Dict[str, Any]],
) -> Dict[str, Any]:
    srs = speech.get("srs") or {}
    sgs = speech.get("sgs") or {}
    srs_pairs = srs.get("finalization_pairs") or []
    sgs_first_chunks = sgs.get("first_chunk_events") or []
    sgs_playback_events = sgs.get("playback_events") or []
    runtime_requests = assistant_runtime_latency.get("request_events") or []
    generation_requests = assistant_runtime_latency.get("generation_requests") or []
    filler_ttft_events = assistant_runtime_latency.get("filler_ttft_events") or []
    pending_windows = assistant_runtime_latency.get("pending_windows") or []
    nca_filler_ready_events = nca_latency.get("filler_generation_events") or []
    nca_response_start_events = nca_latency.get("response_start_events") or []
    nca_filler_race_events = nca_latency.get("filler_race_events") or []

    filler_turns: List[Dict[str, Any]] = []

    for turn in turns:
        turn_number = turn.get("turn_number")
        turn_start = turn.get("start_timestamp")
        turn_end = turn.get("end_timestamp")
        if not turn_start:
            continue

        request_event = _first_event_after(runtime_requests, start_ts=turn_start, end_ts=turn_end)
        if not request_event:
            request_event = {"timestamp": turn_start}
        request_ts = request_event.get("timestamp")

        filler_ttft_event = _first_event_after(filler_ttft_events, start_ts=request_ts, end_ts=turn_end)
        filler_tts_request = _first_event_after(generation_requests, start_ts=request_ts, end_ts=turn_end)
        if not filler_ttft_event or not filler_tts_request:
            continue

        sgs_first_chunk_event = _first_event_after(
            sgs_first_chunks,
            start_ts=filler_tts_request.get("timestamp"),
            end_ts=turn_end,
            predicate=lambda event: event.get("sseq") == filler_tts_request.get("sseq"),
        )
        if not sgs_first_chunk_event:
            sgs_first_chunk_event = _first_event_after(
                sgs_first_chunks,
                start_ts=filler_tts_request.get("timestamp"),
                end_ts=turn_end,
            )
        filler_playback_terminal = _first_event_after(
            sgs_playback_events,
            start_ts=(sgs_first_chunk_event or {}).get("timestamp") or filler_tts_request.get("timestamp"),
            end_ts=turn_end,
            predicate=lambda event: event.get("sseq") == filler_tts_request.get("sseq"),
        )
        agent_tts_request = _first_event_after(
            generation_requests,
            start_ts=filler_tts_request.get("timestamp"),
            end_ts=turn_end,
            predicate=lambda event: (event.get("sseq") or -1) > (filler_tts_request.get("sseq") or -1)
            and event.get("is_final") is False,
        )
        agent_first_chunk_event = None
        if agent_tts_request:
            agent_first_chunk_event = _first_event_after(
                sgs_first_chunks,
                start_ts=agent_tts_request.get("timestamp"),
                end_ts=turn_end,
                predicate=lambda event: event.get("sseq") == agent_tts_request.get("sseq"),
            )
            if not agent_first_chunk_event:
                agent_first_chunk_event = _first_event_after(
                    sgs_first_chunks,
                    start_ts=agent_tts_request.get("timestamp"),
                    end_ts=turn_end,
                )
        agent_playback_start_proxy_ts = None
        if agent_first_chunk_event:
            agent_playback_start_proxy_ts = _later_timestamp(
                (filler_playback_terminal or {}).get("timestamp"),
                agent_first_chunk_event.get("timestamp"),
            )

        pending_window = _last_event_before(
            pending_windows,
            anchor_ts=request_ts,
            max_gap_ms=250.0,
            predicate=lambda event: event.get("finalize_timestamp") is not None,
        )
        matched_srs_pair = None
        if pending_window:
            matched_srs_pair = _last_event_before(
                srs_pairs,
                anchor_ts=pending_window.get("set_timestamp"),
                max_gap_ms=250.0,
                predicate=lambda event: event.get("final_timestamp") is not None,
            )
        if not matched_srs_pair:
            matched_srs_pair = _last_event_before(
                srs_pairs,
                anchor_ts=request_ts,
                max_gap_ms=2500.0,
                predicate=lambda event: event.get("final_timestamp") is not None,
            )

        nca_filler_ready = _first_event_after(nca_filler_ready_events, start_ts=request_ts, end_ts=turn_end)
        nca_filler_response_start = _first_event_after(
            nca_response_start_events,
            start_ts=(nca_filler_ready or {}).get("timestamp") or request_ts,
            end_ts=turn_end,
            predicate=lambda event: event.get("component") == "filler",
        )
        nca_filler_race = _first_event_after(nca_filler_race_events, start_ts=request_ts, end_ts=turn_end)

        filler_turns.append(
            {
                "turn_number": turn_number,
                "user_transcript": turn.get("user_transcript"),
                "timestamps": {
                    "matched_interim_timestamp": (matched_srs_pair or {}).get("interim_timestamp"),
                    "matched_final_timestamp": (matched_srs_pair or {}).get("final_timestamp"),
                    "pending_set_timestamp": (pending_window or {}).get("set_timestamp"),
                    "pending_finalize_timestamp": (pending_window or {}).get("finalize_timestamp"),
                    "request_timestamp": request_ts,
                    "nca_filler_ready_timestamp": (nca_filler_ready or {}).get("timestamp"),
                    "nca_filler_response_start_timestamp": (nca_filler_response_start or {}).get("timestamp"),
                    "filler_tts_request_timestamp": filler_tts_request.get("timestamp"),
                    "filler_first_chunk_timestamp": (sgs_first_chunk_event or {}).get("timestamp"),
                    "filler_playback_terminal_timestamp": (filler_playback_terminal or {}).get("timestamp"),
                    "filler_playback_terminal_state": (filler_playback_terminal or {}).get("state"),
                    "agent_tts_request_timestamp": (agent_tts_request or {}).get("timestamp"),
                    "agent_first_chunk_timestamp": (agent_first_chunk_event or {}).get("timestamp"),
                    "agent_playback_start_proxy_timestamp": agent_playback_start_proxy_ts,
                },
                "segments_ms": {
                    "srs_matched_interim_to_final_ms": (matched_srs_pair or {}).get("duration_ms"),
                    "assistant_runtime_pending_window_ms": (pending_window or {}).get("pending_merge_window_ms"),
                    "assistant_runtime_request_to_filler_ttft_ms": _delta_ms(request_ts, filler_ttft_event.get("timestamp")),
                    "assistant_runtime_request_to_filler_tts_send_ms": _delta_ms(
                        request_ts, filler_tts_request.get("timestamp")
                    ),
                    "nca_request_to_filler_ready_ms": _delta_ms(request_ts, (nca_filler_ready or {}).get("timestamp")),
                    "nca_filler_ready_to_response_start_ms": _delta_ms(
                        (nca_filler_ready or {}).get("timestamp"),
                        (nca_filler_response_start or {}).get("timestamp"),
                    ),
                    "nca_filler_race_ms": (nca_filler_race or {}).get("duration_ms"),
                    "tts_send_to_first_chunk_ms": _delta_ms(
                        filler_tts_request.get("timestamp"),
                        (sgs_first_chunk_event or {}).get("timestamp"),
                    ),
                    "audible_filler_from_request_ms": _delta_ms(
                        request_ts,
                        (sgs_first_chunk_event or {}).get("timestamp"),
                    ),
                    "audible_filler_from_matched_interim_ms": _delta_ms(
                        (matched_srs_pair or {}).get("interim_timestamp"),
                        (sgs_first_chunk_event or {}).get("timestamp"),
                    ),
                    "user_speak_end_to_filler_audible_ms": _delta_ms(
                        (matched_srs_pair or {}).get("interim_timestamp"),
                        (sgs_first_chunk_event or {}).get("timestamp"),
                    ),
                    "filler_playback_terminal_to_agent_playback_start_ms": _delta_ms(
                        (filler_playback_terminal or {}).get("timestamp"),
                        agent_playback_start_proxy_ts,
                    ),
                    "filler_audio_end_to_agent_audible_ms": _delta_ms(
                        (filler_playback_terminal or {}).get("timestamp"),
                        agent_playback_start_proxy_ts,
                    ),
                    "user_speak_end_to_agent_audible_ms": _delta_ms(
                        (matched_srs_pair or {}).get("interim_timestamp"),
                        agent_playback_start_proxy_ts,
                    ),
                },
            }
        )

    return {
        "filler_turns": filler_turns,
        "coverage": {
            "srs_finalization_pairs": len(srs_pairs),
            "runtime_request_events": len(runtime_requests),
            "runtime_generation_requests": len(generation_requests),
            "runtime_filler_ttft_events": len(filler_ttft_events),
            "runtime_pending_windows": len(pending_windows),
            "nca_filler_generation_events": len(nca_filler_ready_events),
            "nca_response_start_events": len(nca_response_start_events),
            "sgs_first_chunk_events": len(sgs_first_chunks),
            "sgs_playback_events": len(sgs_playback_events),
        },
    }


def _build_layer_diagnostics(
    *,
    component_coverage: Dict[str, Any],
    speech: Dict[str, Any],
    assistant_runtime_latency: Dict[str, Any],
    nca_latency: Dict[str, Any],
    turns: List[Dict[str, Any]],
    manual_rca_view: Dict[str, Any],
) -> List[Dict[str, Any]]:
    counts = component_coverage.get("counts") or {}
    srs = speech.get("srs") or {}
    sgs = speech.get("sgs") or {}
    filler_turns = manual_rca_view.get("filler_turns") or []

    assistant_runtime_error_count = sum(
        1
        for turn in turns
        for anomaly in (turn.get("anomalies") or [])
        if anomaly.get("type") == "assistant_runtime_error"
    )
    nca_warning_count = sum(
        1
        for turn in turns
        for anomaly in (turn.get("anomalies") or [])
        if anomaly.get("type") == "nca_warning"
    )
    gmg_warning_count = sum(
        1
        for turn in turns
        for anomaly in (turn.get("anomalies") or [])
        if anomaly.get("type") == "gmg_warning"
    )
    tooling_failed_count = sum(
        1
        for turn in turns
        for call in (turn.get("tool_calls") or [])
        if str(call.get("status") or "").lower() == "failed"
    )
    tooling_total_count = sum(len(turn.get("tool_calls") or []) for turn in turns)
    llm_totals = [
        (turn.get("latency_breakdown") or {}).get("llm_total_ms")
        for turn in turns
        if (turn.get("latency_breakdown") or {}).get("llm_total_ms") is not None
    ]

    layers = [
        {
            "layer": "User/PBX",
            "coverage": "blind",
            "evidence_level": "blind",
            "component_count": 0,
            "key_metrics": {
                "device_or_pbx_telemetry": "not_observed",
                "audible_filler_budget_ms": None,
            },
            "issue_signals": [],
            "blind_spots": ["No direct PBX/network/device playback telemetry in saved trace."],
        },
        {
            "layer": "SRS/ASR",
            "coverage": "observed" if counts.get("cprc_srs", 0) else "missing",
            "evidence_level": "observed" if srs.get("linked") else "partial",
            "component_count": counts.get("cprc_srs", 0),
            "key_metrics": {
                "linked": srs.get("linked"),
                "transcript_events": len(srs.get("transcript_events") or []),
                "finalization_pairs": len(srs.get("finalization_pairs") or []),
                "interim_to_final_avg_ms": _avg_numeric(
                    pair.get("duration_ms") for pair in (srs.get("finalization_pairs") or [])
                ),
                "asr_avg_ms": ((srs.get("latency") or {}).get("asr_latency_ms") or {}).get("avg_ms"),
                "iva_delivery_avg_ms": ((srs.get("latency") or {}).get("iva_delivery_latency_ms") or {}).get("avg_ms"),
                "warning_count": srs.get("warning_count"),
                "error_count": srs.get("error_count"),
            },
            "issue_signals": [
                f"interim->final max={_fmt_ms(max((pair.get('duration_ms') or 0) for pair in (srs.get('finalization_pairs') or [])))}"
                if (srs.get("finalization_pairs") or [])
                else None,
                f"srs warnings={srs.get('warning_count')}" if srs.get("warning_count") else None,
                f"srs errors={srs.get('error_count')}" if srs.get("error_count") else None,
            ],
            "blind_spots": [],
        },
        {
            "layer": "assistant_runtime",
            "coverage": "observed" if counts.get("assistant_runtime", 0) else "missing",
            "evidence_level": "observed" if assistant_runtime_latency.get("request_events") else "partial",
            "component_count": counts.get("assistant_runtime", 0),
            "key_metrics": {
                "request_events": len(assistant_runtime_latency.get("request_events") or []),
                "generation_requests": len(assistant_runtime_latency.get("generation_requests") or []),
                "filler_ttft_events": len(assistant_runtime_latency.get("filler_ttft_events") or []),
                "filler_ttft_avg_ms": _avg_numeric(
                    event.get("ttft_ms") for event in (assistant_runtime_latency.get("filler_ttft_events") or [])
                ),
                "pending_windows": len(assistant_runtime_latency.get("pending_windows") or []),
                "pending_window_avg_ms": _avg_numeric(
                    event.get("pending_merge_window_ms") for event in (assistant_runtime_latency.get("pending_windows") or [])
                ),
                "turn_error_anomalies": assistant_runtime_error_count,
            },
            "issue_signals": [
                f"runtime pending avg={_fmt_ms(_avg_numeric(event.get('pending_merge_window_ms') for event in (assistant_runtime_latency.get('pending_windows') or [])))}"
                if (assistant_runtime_latency.get("pending_windows") or [])
                else None,
                f"runtime filler ttft avg={_fmt_ms(_avg_numeric(event.get('ttft_ms') for event in (assistant_runtime_latency.get('filler_ttft_events') or [])))}"
                if (assistant_runtime_latency.get("filler_ttft_events") or [])
                else None,
                f"assistant_runtime anomalies={assistant_runtime_error_count}" if assistant_runtime_error_count else None,
            ],
            "blind_spots": [],
        },
        {
            "layer": "NCA orchestration",
            "coverage": "observed" if counts.get("nca", 0) else "missing",
            "evidence_level": "observed" if counts.get("nca", 0) else "blind",
            "component_count": counts.get("nca", 0),
            "key_metrics": {
                "filler_race_events": len(nca_latency.get("filler_race_events") or []),
                "filler_race_avg_ms": _avg_numeric(
                    event.get("duration_ms") for event in (nca_latency.get("filler_race_events") or [])
                ),
                "filler_ready_events": len(nca_latency.get("filler_generation_events") or []),
                "response_start_events": len(nca_latency.get("response_start_events") or []),
                "filler_ready_to_response_start_avg_ms": _avg_numeric(
                    turn.get("segments_ms", {}).get("nca_filler_ready_to_response_start_ms")
                    for turn in filler_turns
                ),
                "turn_warning_anomalies": nca_warning_count,
            },
            "issue_signals": [
                f"filler race avg={_fmt_ms(_avg_numeric(event.get('duration_ms') for event in (nca_latency.get('filler_race_events') or [])))}"
                if (nca_latency.get("filler_race_events") or [])
                else None,
                f"filler ready->response start avg={_fmt_ms(_avg_numeric(turn.get('segments_ms', {}).get('nca_filler_ready_to_response_start_ms') for turn in filler_turns))}"
                if filler_turns
                else None,
                f"nca warnings={nca_warning_count}" if nca_warning_count else None,
            ],
            "blind_spots": [],
        },
        {
            "layer": "GMG/LLM",
            "coverage": "observed" if counts.get("gmg", 0) else "partial",
            "evidence_level": "derived" if llm_totals else "blind",
            "component_count": counts.get("gmg", 0),
            "key_metrics": {
                "turns_with_llm": len(llm_totals),
                "llm_total_avg_ms": _avg_numeric(llm_totals),
                "llm_total_max_ms": max(llm_totals) if llm_totals else None,
                "turn_warning_anomalies": gmg_warning_count,
            },
            "issue_signals": [
                f"llm total max={_fmt_ms(max(llm_totals))}" if llm_totals else None,
                f"gmg warnings={gmg_warning_count}" if gmg_warning_count else None,
            ],
            "blind_spots": [],
        },
        {
            "layer": "Tooling",
            "coverage": "observed" if tooling_total_count else "partial",
            "evidence_level": "derived" if tooling_total_count else "blind",
            "component_count": tooling_total_count,
            "key_metrics": {
                "tool_call_count": tooling_total_count,
                "failed_tool_calls": tooling_failed_count,
                "tools_observed": sorted(
                    {
                        str(call.get("tool_name") or "unknown")
                        for turn in turns
                        for call in (turn.get("tool_calls") or [])
                    }
                ),
            },
            "issue_signals": [
                f"failed tools={tooling_failed_count}" if tooling_failed_count else None,
            ],
            "blind_spots": [],
        },
        {
            "layer": "TTS/playback",
            "coverage": "observed" if counts.get("cprc_sgs", 0) else "missing",
            "evidence_level": "observed" if sgs.get("linked") else "partial",
            "component_count": counts.get("cprc_sgs", 0),
            "key_metrics": {
                "linked": sgs.get("linked"),
                "request_count": sgs.get("request_count"),
                "cancel_count": sgs.get("cancel_count"),
                "first_chunk_events": len(sgs.get("first_chunk_events") or []),
                "playback_events": len(sgs.get("playback_events") or []),
                "ttfc_avg_ms": ((sgs.get("latency") or {}).get("ttfc_ms") or {}).get("avg_ms"),
                "playback_avg_ms": ((sgs.get("latency") or {}).get("playback_duration_ms") or {}).get("avg_ms"),
                "filler_to_agent_playback_gap_avg_ms": _avg_numeric(
                    turn.get("segments_ms", {}).get("filler_playback_terminal_to_agent_playback_start_ms")
                    for turn in filler_turns
                ),
                "disconnect_events": len(sgs.get("disconnect_events") or []),
            },
            "issue_signals": [
                f"tts ttfc avg={_fmt_ms(((sgs.get('latency') or {}).get('ttfc_ms') or {}).get('avg_ms'))}"
                if ((sgs.get("latency") or {}).get("ttfc_ms") or {}).get("avg_ms") is not None
                else None,
                f"playback avg={_fmt_ms(((sgs.get('latency') or {}).get('playback_duration_ms') or {}).get('avg_ms'))}"
                if ((sgs.get("latency") or {}).get("playback_duration_ms") or {}).get("avg_ms") is not None
                else None,
                f"filler audio end -> agent audible avg={_fmt_ms(_avg_numeric((turn.get('segments_ms', {}).get('filler_audio_end_to_agent_audible_ms') if turn.get('segments_ms', {}).get('filler_audio_end_to_agent_audible_ms') is not None else turn.get('segments_ms', {}).get('filler_playback_terminal_to_agent_playback_start_ms')) for turn in filler_turns))}"
                if filler_turns
                else None,
                f"sgs disconnects={len(sgs.get('disconnect_events') or [])}" if (sgs.get("disconnect_events") or []) else None,
            ],
            "blind_spots": [
                "Agent playback start uses SGS first-chunk proxy because SGS logs do not emit a direct playback-start event."
            ],
        },
    ]

    for layer in layers:
        layer["issue_signals"] = [signal for signal in (layer.get("issue_signals") or []) if signal]
        layer["blind_spots"] = [spot for spot in (layer.get("blind_spots") or []) if spot]

    return layers


def _manual_rca_turn_map(manual_rca_view: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    turn_map: Dict[int, Dict[str, Any]] = {}
    for filler_turn in manual_rca_view.get("filler_turns") or []:
        turn_number = filler_turn.get("turn_number")
        if isinstance(turn_number, int):
            turn_map[turn_number] = filler_turn
    return turn_map


def _tool_summary(turn: Dict[str, Any]) -> Dict[str, Any]:
    tool_calls = turn.get("tool_calls") or []
    total_ms = sum(
        float(call.get("duration_ms"))
        for call in tool_calls
        if call.get("duration_ms") is not None
    )
    top_call = None
    top_duration = None
    for call in tool_calls:
        duration = call.get("duration_ms")
        if duration is None:
            continue
        numeric = float(duration)
        if top_duration is None or numeric > top_duration:
            top_call = call
            top_duration = numeric
    return {
        "total_ms": total_ms if tool_calls else None,
        "top_call": top_call,
        "top_duration_ms": top_duration,
    }


def _primary_bottleneck(turn: Dict[str, Any], manual_turn: Dict[str, Any] | None) -> Dict[str, Any]:
    manual_segments = (manual_turn or {}).get("segments_ms") or {}
    tool_summary = _tool_summary(turn)
    llm_total_ms = (turn.get("latency_breakdown") or {}).get("llm_total_ms")

    candidates = [
        {
            "label": "STT finalization",
            "value_ms": manual_segments.get("srs_matched_interim_to_final_ms"),
            "owner": "SRS/ASR",
        },
        {
            "label": "runtime->filler",
            "value_ms": manual_segments.get("assistant_runtime_request_to_filler_tts_send_ms"),
            "owner": "assistant_runtime",
        },
        {
            "label": "NCA filler gap",
            "value_ms": manual_segments.get("nca_filler_ready_to_response_start_ms"),
            "owner": "NCA orchestration",
        },
        {
            "label": "TTS first chunk",
            "value_ms": manual_segments.get("tts_send_to_first_chunk_ms"),
            "owner": "TTS/playback",
        },
        {
            "label": "filler audio end -> agent audible",
            "value_ms": (
                manual_segments.get("filler_audio_end_to_agent_audible_ms")
                if manual_segments.get("filler_audio_end_to_agent_audible_ms") is not None
                else manual_segments.get("filler_playback_terminal_to_agent_playback_start_ms")
            ),
            "owner": "TTS/playback",
        },
        {
            "label": "LLM total",
            "value_ms": llm_total_ms,
            "owner": "GMG/LLM",
        },
    ]
    if tool_summary.get("top_duration_ms") is not None:
        top_call = tool_summary.get("top_call") or {}
        candidates.append(
            {
                "label": top_call.get("tool_name") or "tooling",
                "value_ms": tool_summary.get("top_duration_ms"),
                "owner": "Tooling",
            }
        )

    viable = [
        candidate
        for candidate in candidates
        if candidate.get("value_ms") is not None and float(candidate["value_ms"]) > 0
    ]
    if not viable:
        return {"label": "none", "value_ms": None, "owner": "unknown"}
    return max(viable, key=lambda item: float(item["value_ms"]))


def _is_turn_user_perceived_slow(row: Dict[str, Any]) -> bool:
    audible_filler_ms = row.get("audible_filler_ms")
    filler_to_agent_gap_ms = row.get("filler_to_agent_gap_ms")
    return bool(
        (audible_filler_ms is not None and float(audible_filler_ms) >= 2500.0)
        or (filler_to_agent_gap_ms is not None and float(filler_to_agent_gap_ms) >= 800.0)
    )


def _is_user_turn_type(turn_type: Any) -> bool:
    return str(turn_type or "").startswith("user_turn")


def _build_turn_markers(turn: Dict[str, Any], row: Dict[str, Any]) -> List[str]:
    markers: List[str] = []

    def add_metric_marker(label: str, value: Any, threshold_ms: float) -> None:
        if value is None:
            return
        if float(value) >= threshold_ms:
            markers.append(f"[SUSPECT] {label}")

    add_metric_marker("audible filler", row.get("audible_filler_ms"), 2500.0)
    add_metric_marker(
        "filler audio end -> agent audible",
        row.get("filler_audio_end_to_agent_audible_ms"),
        800.0,
    )
    add_metric_marker("STT lag", row.get("stt_lag_ms"), 800.0)
    add_metric_marker("runtime->filler", row.get("runtime_to_filler_ms"), 800.0)
    add_metric_marker("LLM total", row.get("llm_ms"), 3000.0)
    add_metric_marker("tool duration", row.get("tool_ms"), 5000.0)
    if row.get("turn_type") != "greeting":
        add_metric_marker("turn total", row.get("total_ms"), 10000.0)

    for contradiction in turn.get("contradictions") or []:
        markers.append(f"[SUSPECT] contradiction:{contradiction.get('type') or 'unknown'}")
    for anomaly in turn.get("anomalies") or []:
        markers.append(f"[SUSPECT] anomaly:{anomaly.get('type') or 'unknown'}")

    return _ordered_unique(markers)


def _is_turn_flagged(turn: Dict[str, Any], row: Dict[str, Any]) -> bool:
    return bool(_build_turn_markers(turn, row))


def _build_turn_summary_matrix(
    *,
    turns: List[Dict[str, Any]],
    manual_rca_view: Dict[str, Any],
) -> List[Dict[str, Any]]:
    manual_turns = _manual_rca_turn_map(manual_rca_view)
    rows: List[Dict[str, Any]] = []

    for turn in turns:
        turn_number = turn.get("turn_number")
        if not isinstance(turn_number, int):
            continue
        manual_turn = manual_turns.get(turn_number)
        segments_ms = (manual_turn or {}).get("segments_ms") or {}
        tool_summary = _tool_summary(turn)
        bottleneck = _primary_bottleneck(turn, manual_turn)
        row = {
            "turn_number": turn_number,
            "turn_type": turn.get("turn_type") or "unknown",
            "transcript": _shorten(str(turn.get("user_transcript") or "N/A"), 80),
            "ai_response": _shorten(str(turn.get("ai_response") or "N/A"), 120),
            "total_ms": turn.get("duration_ms"),
            "audible_filler_ms": segments_ms.get("audible_filler_from_request_ms"),
            "user_speak_end_to_filler_audible_ms": segments_ms.get("user_speak_end_to_filler_audible_ms"),
            "user_speak_end_to_agent_audible_ms": segments_ms.get("user_speak_end_to_agent_audible_ms"),
            "filler_audio_end_to_agent_audible_ms": (
                segments_ms.get("filler_audio_end_to_agent_audible_ms")
                if segments_ms.get("filler_audio_end_to_agent_audible_ms") is not None
                else segments_ms.get("filler_playback_terminal_to_agent_playback_start_ms")
            ),
            "filler_to_agent_gap_ms": (
                segments_ms.get("filler_audio_end_to_agent_audible_ms")
                if segments_ms.get("filler_audio_end_to_agent_audible_ms") is not None
                else segments_ms.get("filler_playback_terminal_to_agent_playback_start_ms")
            ),
            "stt_lag_ms": segments_ms.get("srs_matched_interim_to_final_ms"),
            "runtime_to_filler_ms": segments_ms.get("assistant_runtime_request_to_filler_tts_send_ms"),
            "tool_ms": tool_summary.get("top_duration_ms"),
            "llm_ms": (turn.get("latency_breakdown") or {}).get("llm_total_ms"),
            "bottleneck": bottleneck.get("label"),
            "owner": bottleneck.get("owner"),
            "bottleneck_duration_ms": bottleneck.get("value_ms"),
        }
        row["user_perceived_slow"] = _is_turn_user_perceived_slow(row)
        row["markers"] = _build_turn_markers(turn, row)
        row["flagged"] = _is_turn_flagged(turn, row)
        rows.append(row)

    return rows


def _normalize_confidence_level(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"low", "medium", "high"}:
        return normalized
    return "unknown"


def _min_confidence_level(left: Any, right: Any) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    left_normalized = _normalize_confidence_level(left)
    right_normalized = _normalize_confidence_level(right)
    if left_normalized == "unknown":
        return right_normalized
    if right_normalized == "unknown":
        return left_normalized
    return min((left_normalized, right_normalized), key=lambda item: order[item])


def _format_component_list(components: Iterable[str]) -> str:
    visible = [str(component) for component in components if component]
    return ", ".join(f"`{component}`" for component in visible)


def _owner_attribution_support(
    *,
    owner: Any,
    primary_turn: Dict[str, Any],
    component_coverage: Dict[str, Any],
) -> Dict[str, Any]:
    normalized_owner = str(owner or "unknown")
    counts = component_coverage.get("counts") or {}
    owner_requirements = {
        "assistant_runtime": [("assistant_runtime",)],
        "NCA orchestration": [("nca",)],
        "SRS/ASR": [("cprc_srs",)],
        "TTS/playback": [("cprc_sgs",)],
        "GMG/LLM": [("gmg", "aig")],
    }

    if normalized_owner in {"unknown", "none", ""}:
        return {
            "confidence": "low",
            "note": "No strong owner signal was isolated from the current trace.",
            "missing_components": [],
        }

    if normalized_owner == "Tooling":
        if primary_turn.get("tool_ms") is not None:
            return {
                "confidence": "high",
                "note": "Top tool timing is directly visible in the traced turn data.",
                "missing_components": [],
            }
        return {
            "confidence": "medium",
            "note": "Tooling is the leading candidate, but the traced turn does not expose a top tool duration.",
            "missing_components": [],
        }

    required_groups = owner_requirements.get(normalized_owner)
    if not required_groups:
        return {
            "confidence": "medium",
            "note": f"{normalized_owner} is inferred from summary signals rather than a direct component-specific trace.",
            "missing_components": [],
        }

    missing_components: List[str] = []
    for group in required_groups:
        if any(int(counts.get(component, 0) or 0) > 0 for component in group):
            continue
        missing_components.extend(group)

    if missing_components:
        return {
            "confidence": "low",
            "note": (
                f"Timing points at {normalized_owner}, but direct {_format_component_list(missing_components)} "
                f"coverage is missing."
            ),
            "missing_components": missing_components,
        }

    return {
        "confidence": "high",
        "note": f"Direct trace coverage exists for the likely owner path: {normalized_owner}.",
        "missing_components": [],
    }


def _build_session_scorecard(
    *,
    session_id: str | None,
    latency_path: str,
    basic_judgment: Dict[str, Any],
    component_coverage: Dict[str, Any],
    turn_summary_matrix: List[Dict[str, Any]],
) -> Dict[str, Any]:
    ranking_pool = [row for row in turn_summary_matrix if _is_user_turn_type(row.get("turn_type"))]
    if not ranking_pool:
        ranking_pool = turn_summary_matrix
    flagged_turns = [row for row in ranking_pool if row.get("flagged")]
    audible_slow_turns = [row for row in ranking_pool if row.get("user_perceived_slow")]
    ranked_turns = sorted(
        ranking_pool,
        key=lambda row: float(row.get("bottleneck_duration_ms") or row.get("total_ms") or 0.0),
        reverse=True,
    )
    primary_turn = ranked_turns[0] if ranked_turns else {}
    outcome_category = basic_judgment.get("outcome_category") or "unknown"
    verdict = outcome_category
    if audible_slow_turns:
        verdict = "audible_delay_detected"
    elif flagged_turns and primary_turn.get("owner") in {"Tooling", "GMG/LLM"}:
        verdict = "long_but_covered"
    elif outcome_category == "no_issue_observed":
        verdict = "healthy"

    likely_owner = primary_turn.get("owner") or basic_judgment.get("owner") or "unknown"
    support = _owner_attribution_support(
        owner=likely_owner,
        primary_turn=primary_turn,
        component_coverage=component_coverage,
    )
    attribution_confidence = _min_confidence_level(
        basic_judgment.get("confidence"),
        support.get("confidence"),
    )

    return {
        "session_id": session_id,
        "path": latency_path,
        "verdict": verdict,
        "user_perceived_slow": bool(audible_slow_turns),
        "primary_bottleneck": primary_turn.get("bottleneck") or "none",
        "owner": likely_owner,
        "likely_owner": likely_owner,
        "confidence": basic_judgment.get("confidence") or "unknown",
        "attribution_confidence": attribution_confidence,
        "owner_note": support.get("note"),
        "owner_missing_components": support.get("missing_components") or [],
        "turn_count": len(turn_summary_matrix),
        "flagged_turn_count": len(flagged_turns),
        "audible_slow_turn_count": len(audible_slow_turns),
        "primary_turn_number": primary_turn.get("turn_number"),
    }


def _build_action_summary(
    *,
    session_scorecard: Dict[str, Any],
    turn_summary_matrix: List[Dict[str, Any]],
    component_coverage: Dict[str, Any],
) -> Dict[str, Any]:
    primary_turn_number = session_scorecard.get("primary_turn_number")
    primary_turn = next(
        (
            row
            for row in turn_summary_matrix
            if row.get("turn_number") == primary_turn_number
        ),
        {},
    )
    likely_owner = session_scorecard.get("likely_owner") or session_scorecard.get("owner") or "unknown"
    attribution_confidence = session_scorecard.get("attribution_confidence") or "unknown"
    missing_owner_components = session_scorecard.get("owner_missing_components") or []
    transcript = primary_turn.get("transcript") or "N/A"
    turn_number = primary_turn.get("turn_number")
    filler_gap_ms = (
        primary_turn.get("filler_audio_end_to_agent_audible_ms")
        if primary_turn.get("filler_audio_end_to_agent_audible_ms") is not None
        else primary_turn.get("filler_to_agent_gap_ms")
    )
    tool_name = primary_turn.get("bottleneck") if likely_owner == "Tooling" else None

    if primary_turn.get("user_perceived_slow") and turn_number is not None:
        customer_impact = f"User likely heard a meaningful delay in turn {turn_number}."
    elif turn_number is not None:
        customer_impact = f"No clear user-perceived delay was detected in the primary turn {turn_number}."
    else:
        customer_impact = "No user turn was available for a customer-impact assessment."

    if turn_number is not None and filler_gap_ms is not None and float(filler_gap_ms) >= 800.0:
        strongest_claim = f"Turn {turn_number} had {_fmt_ms(filler_gap_ms)} of silence after filler audio ended."
    elif (
        turn_number is not None
        and likely_owner == "Tooling"
        and primary_turn.get("tool_ms") is not None
        and filler_gap_ms is not None
    ):
        strongest_claim = (
            f"Turn {turn_number} spent {_fmt_ms(primary_turn.get('tool_ms'))} in `{tool_name or 'tooling'}`, "
            f"but only {_fmt_ms(filler_gap_ms)} elapsed after filler audio ended."
        )
    elif turn_number is not None and primary_turn.get("user_speak_end_to_agent_audible_ms") is not None:
        strongest_claim = (
            f"Turn {turn_number} reached agent audio after "
            f"{_fmt_ms(primary_turn.get('user_speak_end_to_agent_audible_ms'))} from user speech end."
        )
    elif turn_number is not None and primary_turn.get("bottleneck_duration_ms") is not None:
        strongest_claim = (
            f"Turn {turn_number} was dominated by `{primary_turn.get('bottleneck') or 'unknown'}` at "
            f"{_fmt_ms(primary_turn.get('bottleneck_duration_ms'))}."
        )
    else:
        strongest_claim = "No single dominant claim could be synthesized from the available turn data."

    if turn_number is not None and missing_owner_components:
        next_action = (
            f"Pull {_format_component_list(missing_owner_components)} coverage for turn {turn_number} "
            f"before assigning owner."
        )
    elif turn_number is not None and likely_owner == "GMG/LLM":
        next_action = f"Inspect LLM timing, warnings, and response path for turn {turn_number}."
    elif turn_number is not None and likely_owner == "assistant_runtime":
        next_action = f"Inspect assistant_runtime filler scheduling and pending-window behavior for turn {turn_number}."
    elif turn_number is not None and likely_owner == "NCA orchestration":
        next_action = f"Inspect NCA filler-ready and ResponseStart sequencing for turn {turn_number}."
    elif turn_number is not None and likely_owner == "TTS/playback":
        next_action = f"Inspect SGS playback ordering and first-chunk timing for turn {turn_number}."
    elif turn_number is not None and likely_owner == "SRS/ASR":
        next_action = f"Inspect STT finalization lag and transcript ordering for turn {turn_number}."
    elif turn_number is not None and likely_owner == "Tooling":
        next_action = (
            f"Inspect `{tool_name or 'tooling'}` in turn {turn_number} and confirm whether the tool is only long "
            f"or actually blocks audio."
        )
    else:
        next_action = "Manual RCA is still required before a focused owner handoff."

    return {
        "customer_impact": customer_impact,
        "worst_turn_number": turn_number,
        "worst_turn_transcript": transcript,
        "strongest_claim": strongest_claim,
        "likely_owner": likely_owner,
        "attribution_confidence": attribution_confidence,
        "owner_note": session_scorecard.get("owner_note") or "No owner note synthesized.",
        "next_action": next_action,
        "component_coverage_gap": _format_component_list(component_coverage.get("missing_components") or []),
    }


def _timeline_line(label: str, value: Any, *, suspect: bool = False) -> str | None:
    if value is None:
        return None
    prefix = "[SUSPECT] " if suspect else ""
    return f"  {prefix}{label:.<36} {_fmt_ms(value)}"


def _build_expanded_timelines(
    *,
    turns: List[Dict[str, Any]],
    turn_summary_matrix: List[Dict[str, Any]],
    manual_rca_view: Dict[str, Any],
) -> List[Dict[str, Any]]:
    manual_turns = _manual_rca_turn_map(manual_rca_view)
    turns_by_number = {
        turn.get("turn_number"): turn
        for turn in turns
        if isinstance(turn.get("turn_number"), int)
    }
    selected_rows = [
        row for row in turn_summary_matrix
        if row.get("flagged") and _is_user_turn_type(row.get("turn_type"))
    ]
    if not selected_rows:
        selected_rows = [row for row in turn_summary_matrix if row.get("flagged")]
    if not selected_rows and turn_summary_matrix:
        selected_rows = [
            max(
                turn_summary_matrix,
                key=lambda row: float(row.get("bottleneck_duration_ms") or row.get("total_ms") or 0.0),
            )
        ]

    timelines: List[Dict[str, Any]] = []
    for row in selected_rows[:3]:
        turn_number = row.get("turn_number")
        turn = turns_by_number.get(turn_number, {})
        manual_turn = manual_turns.get(turn_number, {})
        segments_ms = manual_turn.get("segments_ms") or {}
        timestamps = manual_turn.get("timestamps") or {}
        tool_summary = _tool_summary(turn)
        markers = set(row.get("markers") or [])
        lines = ["anchor: matched usable interim = T+0ms"]
        ordered_lines = [
            _timeline_line(
                "isFinal lag",
                segments_ms.get("srs_matched_interim_to_final_ms"),
                suspect="[SUSPECT] STT lag" in markers,
            ),
            _timeline_line(
                "runtime -> filler TTS send",
                segments_ms.get("assistant_runtime_request_to_filler_tts_send_ms"),
                suspect="[SUSPECT] runtime->filler" in markers,
            ),
            _timeline_line("nca filler ready", segments_ms.get("nca_request_to_filler_ready_ms")),
            _timeline_line("filler ready -> ResponseStart", segments_ms.get("nca_filler_ready_to_response_start_ms")),
            _timeline_line("tts first chunk", segments_ms.get("tts_send_to_first_chunk_ms")),
            _timeline_line(
                "user speak end -> filler audible",
                segments_ms.get("user_speak_end_to_filler_audible_ms"),
            ),
            _timeline_line(
                "user speak end -> agent audible",
                segments_ms.get("user_speak_end_to_agent_audible_ms"),
            ),
            _timeline_line(
                "audible filler",
                segments_ms.get("audible_filler_from_request_ms"),
                suspect="[SUSPECT] audible filler" in markers,
            ),
            _timeline_line(
                "filler audio end -> agent audible",
                (
                    segments_ms.get("filler_audio_end_to_agent_audible_ms")
                    if segments_ms.get("filler_audio_end_to_agent_audible_ms") is not None
                    else segments_ms.get("filler_playback_terminal_to_agent_playback_start_ms")
                ),
                suspect="[SUSPECT] filler audio end -> agent audible" in markers,
            ),
            _timeline_line(
                "llm total",
                (turn.get("latency_breakdown") or {}).get("llm_total_ms"),
                suspect="[SUSPECT] LLM total" in markers,
            ),
            _timeline_line(
                f"tool: {(tool_summary.get('top_call') or {}).get('tool_name') or 'none'}",
                tool_summary.get("top_duration_ms"),
                suspect="[SUSPECT] tool duration" in markers,
            ),
        ]
        lines.extend(line for line in ordered_lines if line)
        if timestamps.get("agent_playback_start_proxy_timestamp"):
            lines.append(f"  agent playback start{' ' * 20} ^ {timestamps['agent_playback_start_proxy_timestamp']}")
        timelines.append(
            {
                "turn_number": turn_number,
                "transcript": row.get("transcript"),
                "ai_response": row.get("ai_response"),
                "selection_reason": "flagged" if row.get("flagged") else "top_bottleneck",
                "lines": lines,
            }
        )

    return timelines


def _build_evidence_registry(
    *,
    turn_summary_matrix: List[Dict[str, Any]],
    layer_diagnostics: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    ranking_pool = [row for row in turn_summary_matrix if _is_user_turn_type(row.get("turn_type"))]
    if not ranking_pool:
        ranking_pool = turn_summary_matrix
    primary_turn = max(
        ranking_pool,
        key=lambda row: float(row.get("bottleneck_duration_ms") or row.get("total_ms") or 0.0),
        default=None,
    )
    if primary_turn:
        metric_specs = (
            ("STT lag", primary_turn.get("stt_lag_ms"), "observed", "SRS/ASR", "manual_rca_view"),
            (
                "runtime->filler",
                primary_turn.get("runtime_to_filler_ms"),
                "observed",
                "assistant_runtime",
                "manual_rca_view",
            ),
            (
                "audible filler",
                primary_turn.get("audible_filler_ms"),
                "derived/proxy",
                "TTS/playback",
                "manual_rca_view",
            ),
            (
                "filler audio end -> agent audible",
                (
                    primary_turn.get("filler_audio_end_to_agent_audible_ms")
                    if primary_turn.get("filler_audio_end_to_agent_audible_ms") is not None
                    else primary_turn.get("filler_to_agent_gap_ms")
                ),
                "derived/proxy",
                "TTS/playback",
                "manual_rca_view",
            ),
        )
        for signal, value, evidence, owner, source in metric_specs:
            if value is None:
                continue
            rows.append(
                {
                    "signal": signal,
                    "value": _fmt_ms(value),
                    "evidence_level": evidence,
                    "owner": owner,
                    "source_ref": source,
                }
            )

    for layer in layer_diagnostics:
        layer_name = layer.get("layer") or "unknown"
        for blind_spot in layer.get("blind_spots") or []:
            rows.append(
                {
                    "signal": f"{layer_name} blind spot",
                    "value": "N/A",
                    "evidence_level": "blind",
                    "owner": layer_name,
                    "source_ref": blind_spot,
                }
            )

    return rows


def _dedupe_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for event in events:
        key = (
            event.get("timestamp"),
            event.get("session_id"),
            event.get("request_id"),
            event.get("sseq"),
            event.get("type"),
            event.get("message"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(event)
    return deduped


def _parse_srs_log(log_path: Path, expected_session_id: str | None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "component": "srs",
        "log_path": str(log_path),
        "expected_session_id": expected_session_id,
        "observed_session_ids": [],
        "linked": False,
        "first_seen": None,
        "last_seen": None,
        "connect_events": [],
        "disconnect_events": [],
        "error_count": 0,
        "warning_count": 0,
        "transcript_events": [],
        "finalization_pairs": [],
        "latency": {
            "asr_latency_ms": {"count": 0, "avg_ms": None, "max_ms": None},
            "iva_delivery_latency_ms": {"count": 0, "avg_ms": None, "max_ms": None},
        },
    }
    if not log_path.exists():
        return payload

    observed_ids: List[str] = []
    asr_values: List[float] = []
    iva_delivery_values: List[float] = []
    transcript_events: List[Dict[str, Any]] = []
    finalization_pairs: List[Dict[str, Any]] = []
    last_non_final_by_words: Dict[int, Dict[str, Any]] = {}

    for raw_line in log_path.read_text(encoding="utf-8").splitlines():
        ts, body = _line_parts(raw_line)
        if ts:
            payload["first_seen"] = payload["first_seen"] or ts
            payload["last_seen"] = ts

        line_ids = _extract_session_ids(raw_line)
        for session_id in line_ids:
            if session_id not in observed_ids:
                observed_ids.append(session_id)

        matched_session_id = _pick_session_id(raw_line, expected_session_id, line_ids)

        if " WARN " in raw_line:
            payload["warning_count"] += 1
        if " ERROR " in raw_line or " failed" in raw_line.lower() or "failure" in raw_line.lower():
            payload["error_count"] += 1

        for marker, event_type in SRS_CONNECT_MARKERS:
            if marker in raw_line:
                payload["connect_events"].append(
                    {
                        "timestamp": ts,
                        "session_id": matched_session_id,
                        "type": event_type,
                        "is_error": False,
                        "message": _shorten(body),
                    }
                )
                break

        for marker, event_type, is_error in SRS_DISCONNECT_MARKERS:
            if marker in raw_line:
                payload["disconnect_events"].append(
                    {
                        "timestamp": ts,
                        "session_id": matched_session_id,
                        "type": event_type,
                        "is_error": is_error or _is_error_line(raw_line),
                        "message": _shorten(body),
                    }
                )
                break

        asr_match = ASR_LATENCY_PATTERN.search(raw_line)
        if asr_match:
            asr_values.append(float(asr_match.group(1)) * 1000.0)

        iva_delivery_match = IVA_DELIVERY_PATTERN.search(raw_line)
        if iva_delivery_match:
            iva_delivery_values.append(float(iva_delivery_match.group(1)) * 1000.0)

        transcript_match = TRANSCRIPT_RESULT_PATTERN.search(raw_line)
        if transcript_match and matched_session_id:
            words = int(transcript_match.group("words"))
            is_final = transcript_match.group("is_final").lower() == "true"
            event = {
                "timestamp": ts,
                "session_id": matched_session_id,
                "is_final": is_final,
                "words": words,
            }
            transcript_events.append(event)
            if is_final:
                previous_event = last_non_final_by_words.get(words)
                lag_ms = _delta_ms(previous_event.get("timestamp") if previous_event else None, ts)
                if previous_event and lag_ms is not None and lag_ms >= 0:
                    finalization_pairs.append(
                        {
                            "interim_timestamp": previous_event["timestamp"],
                            "final_timestamp": ts,
                            "words": words,
                            "duration_ms": lag_ms,
                        }
                    )
            else:
                last_non_final_by_words[words] = event

    payload["observed_session_ids"] = observed_ids
    payload["linked"] = bool(expected_session_id and expected_session_id in observed_ids)
    payload["connect_events"] = _dedupe_events(payload["connect_events"])
    payload["disconnect_events"] = _dedupe_events(payload["disconnect_events"])
    payload["transcript_events"] = transcript_events
    payload["finalization_pairs"] = finalization_pairs
    payload["latency"]["asr_latency_ms"] = _latency_stats(asr_values)
    payload["latency"]["iva_delivery_latency_ms"] = _latency_stats(iva_delivery_values)
    return payload


def _parse_sgs_log(log_path: Path, expected_session_id: str | None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "component": "sgs",
        "log_path": str(log_path),
        "expected_session_id": expected_session_id,
        "observed_session_ids": [],
        "linked": False,
        "first_seen": None,
        "last_seen": None,
        "disconnect_events": [],
        "request_count": 0,
        "cancel_count": 0,
        "last_audio_end": None,
        "generate_events": [],
        "first_chunk_events": [],
        "playback_events": [],
        "latency": {
            "ttfc_ms": {"count": 0, "avg_ms": None, "max_ms": None},
            "playback_duration_ms": {"count": 0, "avg_ms": None, "max_ms": None},
        },
    }
    if not log_path.exists():
        return payload

    observed_ids: List[str] = []
    ttfc_values: List[float] = []
    playback_values: List[float] = []
    generate_events: List[Dict[str, Any]] = []
    first_chunk_events: List[Dict[str, Any]] = []
    playback_events: List[Dict[str, Any]] = []

    for raw_line in log_path.read_text(encoding="utf-8").splitlines():
        ts, body = _line_parts(raw_line)
        if ts:
            payload["first_seen"] = payload["first_seen"] or ts
            payload["last_seen"] = ts

        line_ids = _extract_session_ids(raw_line)
        for session_id in line_ids:
            if session_id not in observed_ids:
                observed_ids.append(session_id)

        matched_session_id = _pick_session_id(raw_line, expected_session_id, line_ids)

        new_generate_match = NEW_GENERATE_PATTERN.search(raw_line)
        if new_generate_match:
            sseq_match = SSEQ_PATTERN.search(raw_line)
            sseq = int(sseq_match.group(1)) if sseq_match else None
            generate_events.append(
                {
                    "timestamp": ts,
                    "request_session_id": new_generate_match.group("request_session_id"),
                    "kind": new_generate_match.group("kind"),
                    "sseq": sseq,
                }
            )
            if new_generate_match.group("kind") == "Request":
                payload["request_count"] += 1
            else:
                payload["cancel_count"] += 1

        ttfc_match = SGS_FIRST_CHUNK_PATTERN.search(raw_line)
        if ttfc_match:
            ttfc_ms = float(ttfc_match.group(1)) * 1000.0
            ttfc_values.append(ttfc_ms)
            request_id_match = REQUEST_ID_PATTERN.search(raw_line)
            request_id = request_id_match.group(1) if request_id_match else None
            first_chunk_events.append(
                {
                    "timestamp": ts,
                    "request_id": request_id,
                    "sseq": _extract_request_sseq(request_id),
                    "latency_ms": ttfc_ms,
                }
            )

        playback_match = PLAYBACK_DURATION_PATTERN.search(raw_line)
        if playback_match:
            duration_ms = float(playback_match.group("duration"))
            playback_values.append(duration_ms)
            request_id_match = REQUEST_ID_PATTERN.search(raw_line)
            request_id = request_id_match.group(1) if request_id_match else None
            playback_events.append(
                {
                    "timestamp": ts,
                    "request_id": request_id,
                    "sseq": int(playback_match.group("sseq")),
                    "state": playback_match.group("state"),
                    "duration_ms": duration_ms,
                }
            )
            if playback_match.group("state") == "interrupted":
                payload["disconnect_events"].append(
                    {
                        "timestamp": ts,
                        "session_id": matched_session_id,
                        "request_id": request_id,
                        "sseq": int(playback_match.group("sseq")),
                        "type": "playback_interrupted",
                        "is_error": False,
                        "message": _shorten(body),
                    }
                )

        if "audio end session_id=" in raw_line:
            payload["last_audio_end"] = ts

        for marker, event_type, is_error in SGS_DISCONNECT_MARKERS:
            if marker in raw_line:
                payload["disconnect_events"].append(
                    {
                        "timestamp": ts,
                        "session_id": matched_session_id,
                        "request_id": REQUEST_ID_PATTERN.search(raw_line).group(1)
                        if REQUEST_ID_PATTERN.search(raw_line)
                        else None,
                        "sseq": int(SSEQ_PATTERN.search(raw_line).group(1))
                        if SSEQ_PATTERN.search(raw_line)
                        else None,
                        "type": event_type,
                        "is_error": is_error,
                        "message": _shorten(body),
                    }
                )
                break

    payload["observed_session_ids"] = observed_ids
    payload["linked"] = bool(expected_session_id and expected_session_id in observed_ids)
    payload["disconnect_events"] = _dedupe_events(payload["disconnect_events"])
    payload["generate_events"] = generate_events
    payload["first_chunk_events"] = first_chunk_events
    payload["playback_events"] = playback_events
    payload["latency"]["ttfc_ms"] = _latency_stats(ttfc_values)
    payload["latency"]["playback_duration_ms"] = _latency_stats(playback_values)
    return payload


def _parse_assistant_runtime_latency(log_path: Path) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "request_events": [],
        "generation_requests": [],
        "filler_ttft_events": [],
        "pending_windows": [],
    }
    if not log_path.exists():
        return payload

    current_pending: Dict[str, Any] | None = None

    for raw_line in log_path.read_text(encoding="utf-8").splitlines():
        ts, _ = _line_parts(raw_line)

        if "Sending request " in raw_line:
            request_payload = _extract_first_json_object(raw_line)
            if isinstance(request_payload, dict):
                request_body = request_payload.get("payload") or {}
                if request_body.get("oneofKind") == "generate":
                    payload["request_events"].append(
                        {
                            "timestamp": ts,
                            "completion_id": request_payload.get("completionId"),
                            "conversation_id": ((request_payload.get("context") or {}).get("conversationId")),
                        }
                    )

        generation_match = AR_GENERATION_REQUEST_PATTERN.search(raw_line)
        if generation_match:
            payload["generation_requests"].append(
                {
                    "timestamp": ts,
                    "sseq": int(generation_match.group("sseq")),
                    "is_final": generation_match.group("is_final").lower() == "true",
                }
            )

        filler_ttft_match = AR_FILLER_TTFT_PATTERN.search(raw_line)
        if filler_ttft_match:
            payload["filler_ttft_events"].append(
                {
                    "timestamp": ts,
                    "ttft_ms": float(filler_ttft_match.group("ttft_ms")),
                }
            )

        pending_match = AR_SET_PENDING_PATTERN.search(raw_line)
        if pending_match:
            current_pending = {
                "timestamp": ts,
                "set_timestamp": ts,
                "from_value": pending_match.group("before"),
                "to_value": pending_match.group("after"),
                "timeout_started_at": None,
                "timeout_cleared_at": None,
                "finalize_timestamp": None,
                "pending_merge_window_ms": None,
            }
            continue

        if "startPendingTranscriptTimeout:" in raw_line and current_pending:
            current_pending["timeout_started_at"] = ts
            continue

        if "clearPendingTranscriptTimeout:" in raw_line and current_pending:
            current_pending["timeout_cleared_at"] = ts
            continue

        if "finalizePendingTranscript:" in raw_line and current_pending:
            current_pending["finalize_timestamp"] = ts
            current_pending["pending_merge_window_ms"] = _delta_ms(current_pending.get("set_timestamp"), ts)
            payload["pending_windows"].append(current_pending)
            current_pending = None

    return payload


def _parse_nca_latency(log_path: Path) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "filler_race_events": [],
        "filler_generation_events": [],
        "response_start_events": [],
    }
    if not log_path.exists():
        return payload

    for raw_line in log_path.read_text(encoding="utf-8").splitlines():
        ts, _ = _line_parts(raw_line)

        race_match = NCA_FILLER_RACE_PATTERN.search(raw_line)
        if race_match:
            payload["filler_race_events"].append(
                {
                    "timestamp": ts,
                    "duration_ms": float(race_match.group("duration_ms")),
                }
            )

        if NCA_FILLER_GENERATION_COMPLETED_PATTERN.search(raw_line):
            payload["filler_generation_events"].append({"timestamp": ts})

        response_start_match = NCA_RESPONSE_START_PATTERN.search(raw_line)
        if response_start_match:
            payload["response_start_events"].append(
                {
                    "timestamp": ts,
                    "component": response_start_match.group("component"),
                }
            )

    return payload


def _fmt_ms(value: Any) -> str:
    if value is None:
        return "N/A"
    numeric = float(value)
    if math.isnan(numeric):
        return "N/A"
    return f"{numeric:.0f} ms"


def _fmt_non_negative_ms(value: Any) -> str:
    if value is None:
        return "N/A"
    numeric = float(value)
    if math.isnan(numeric):
        return "N/A"
    if numeric < 0:
        return "0 ms"
    return f"{numeric:.0f} ms"


def _ordered_unique(values: Iterable[Any]) -> List[Any]:
    seen = OrderedDict()
    for value in values:
        if value in (None, "", [], {}):
            continue
        seen[value] = True
    return list(seen.keys())


def _extract_first_json_object(line: str) -> Any:
    match = JSON_OBJECT_PATTERN.search(line)
    if not match:
        return None
    return _safe_json_from_match(match.group(1))


def _flatten_feature_flags(flags: Dict[str, Any]) -> Dict[str, Any]:
    flattened: Dict[str, Any] = {}
    for key in (
        "agent_type",
        "hangup_tool_enabled",
        "language_auto_detection",
        "enabled_contextual_handover",
        "embedded_qa_context_size",
        "dual_llm_service_tier",
        "_filler_phrase_timeout_ms",
    ):
        if key in flags:
            flattened[key] = flags[key]
    nova_config = flags.get("nova_config")
    if isinstance(nova_config, dict):
        if "solution" in nova_config:
            flattened["solution"] = nova_config["solution"]
        if "model_group_tag" in nova_config:
            flattened["model_group_tag"] = nova_config["model_group_tag"]
        if "enableFiller" in nova_config:
            flattened["enable_filler"] = nova_config["enableFiller"]
        if "enableIndependenceFiller" in nova_config:
            flattened["enable_independence_filler"] = nova_config["enableIndependenceFiller"]
    llm_settings = flags.get("llm_settings")
    if isinstance(llm_settings, dict):
        flattened["llm_default"] = llm_settings.get("default")
        flattened["llm_default_model_name"] = llm_settings.get("default_model_name")
        flattened["llm_fallback"] = llm_settings.get("fallback")
        flattened["llm_fallback_model_name"] = llm_settings.get("fallback_model_name")
    turn_detector = flags.get("turn_detector")
    if isinstance(turn_detector, dict):
        flattened["turn_detector"] = {
            "enabled": turn_detector.get("enabled"),
            "timeout": turn_detector.get("timeout"),
            "incomplete_pattern_check": turn_detector.get("incomplete_pattern_check"),
        }
    dynamic_filler = flags.get("dynamic_filler_phrases")
    if isinstance(dynamic_filler, dict):
        flattened["dynamic_filler_phrases"] = dynamic_filler
    latency_use_dual_llm = flags.get("latency_use_dual_llm")
    if isinstance(latency_use_dual_llm, dict):
        flattened["latency_use_dual_llm"] = latency_use_dual_llm
    return flattened


def _parse_start_conversation(assistant_runtime_log: Path) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "is_nova": False,
        "account_id": None,
        "request_id": None,
        "status": "not_observed",
        "started_at": None,
        "completed_at": None,
        "duration_ms": None,
        "conversation_id": None,
        "assistant_id": None,
        "grpc_address": None,
        "source": None,
    }
    if not assistant_runtime_log.exists():
        return payload

    start_dt = None
    end_dt = None

    for raw_line in assistant_runtime_log.read_text(encoding="utf-8").splitlines():
        ts, _ = _line_parts(raw_line)
        create_match = CREATE_NOVA_REQUEST_PATTERN.search(raw_line)
        if create_match:
            payload["is_nova"] = True
            payload["account_id"] = int(create_match.group("account_id"))
            payload["request_id"] = create_match.group("request_id")
            payload["started_at"] = ts
            payload["source"] = "assistant_runtime"
            start_dt = parse_timestamp(ts) if ts else None
            continue

        if START_CONVERSATION_OK_PATTERN.search(raw_line):
            payload["is_nova"] = True
            payload["status"] = "success"
            payload["completed_at"] = ts
            end_dt = parse_timestamp(ts) if ts else None
            body = _extract_first_json_object(raw_line)
            if isinstance(body, dict):
                payload["conversation_id"] = (
                    body.get("conversation", {}).get("id")
                    or body.get("id")
                    or payload.get("conversation_id")
                )
                payload["assistant_id"] = (
                    body.get("assistant", {}).get("id")
                    or body.get("assistantId")
                    or payload.get("assistant_id")
                )
                payload["grpc_address"] = (
                    body.get("systemMetadata", {}).get("address")
                    or payload.get("grpc_address")
                )
            continue

        created_match = NOVA_CONVERSATION_CREATED_PATTERN.search(raw_line)
        if created_match:
            payload["is_nova"] = True
            payload["status"] = "success"
            payload["completed_at"] = ts
            payload["conversation_id"] = created_match.group("conversation_id")
            payload["request_id"] = created_match.group("request_id")
            end_dt = parse_timestamp(ts) if ts else end_dt
            continue

        if "Nova Conversation is created:" in raw_line:
            payload["is_nova"] = True
            payload["status"] = "success"
            payload["completed_at"] = ts
            end_dt = parse_timestamp(ts) if ts else end_dt
            body = _extract_first_json_object(raw_line)
            if isinstance(body, dict):
                payload["conversation_id"] = body.get("conversationId") or payload.get("conversation_id")
                payload["assistant_id"] = body.get("assistantId") or payload.get("assistant_id")
                payload["grpc_address"] = body.get("grpcAddress") or payload.get("grpc_address")

        if "calculateFeatureFlags final feature flags:" in raw_line and '"agent_type":"nova"' in raw_line:
            payload["is_nova"] = True
        if "agentType\":\"nova\"" in raw_line or "nova-assistant" in raw_line:
            payload["is_nova"] = True

    if start_dt and end_dt and end_dt >= start_dt:
        payload["duration_ms"] = (end_dt - start_dt).total_seconds() * 1000.0

    return payload


def _parse_assistant_configuration(session_dir: Path) -> Dict[str, Any]:
    assistant_runtime_log = session_dir / "assistant_runtime_message.log"
    nca_log = session_dir / "nca_message.log"
    agent_service_log = session_dir / "agent_service_message.log"

    payload: Dict[str, Any] = {
        "source": None,
        "assistant_id": None,
        "external_assistant_id": None,
        "configuration_provider_url": None,
        "application_id": None,
        "solution": None,
        "group_tag": None,
        "voice_id": None,
        "languages": [],
        "website": None,
        "tool_names": [],
        "tool_count": 0,
        "raw_enabled_skills": [],
        "graph_bundle": None,
        "graph_skills": [],
        "feature_flags": {},
        "nca_flag_evaluations": {},
    }

    if agent_service_log.exists():
        payload["source"] = "agent_service"
        for raw_line in agent_service_log.read_text(encoding="utf-8").splitlines():
            if payload["assistant_id"] is None and "Getting nova assistant configuration" in raw_line:
                match = re.search(r"assistantId\s+([0-9a-f-]{36})", raw_line, re.IGNORECASE)
                if match:
                    payload["assistant_id"] = match.group(1)
            if not payload["raw_enabled_skills"]:
                match = RAW_ENABLED_SKILLS_PATTERN.search(raw_line)
                if match:
                    parsed = _safe_json_from_match(match.group(1))
                    if isinstance(parsed, list):
                        payload["raw_enabled_skills"] = parsed
            if payload["graph_bundle"] is None:
                match = GRAPH_SKILLS_PATTERN.search(raw_line)
                if match:
                    payload["graph_bundle"] = match.group(1).strip()
                    payload["graph_skills"] = [item.strip() for item in match.group(2).split(",") if item.strip()]
            if payload["solution"] is None or payload["group_tag"] is None:
                match = PBX_BUILDER_PATTERN.search(raw_line)
                if match:
                    payload["solution"] = payload["solution"] or match.group("solution").strip()
                    payload["group_tag"] = payload["group_tag"] or match.group("group_tag").strip()
            if not payload["feature_flags"]:
                match = PARSED_FLAGS_PATTERN.search(raw_line)
                if match:
                    parsed = _safe_json_from_match(match.group(1))
                    if isinstance(parsed, dict):
                        payload["feature_flags"] = _flatten_feature_flags(parsed)
                        payload["solution"] = payload["solution"] or payload["feature_flags"].get("solution")
                        payload["group_tag"] = payload["group_tag"] or payload["feature_flags"].get("model_group_tag")

    for raw_line in nca_log.read_text(encoding="utf-8").splitlines() if nca_log.exists() else []:
        if payload["external_assistant_id"] is None or payload["configuration_provider_url"] is None:
            match = EXTERNAL_LOOKUP_PATTERN.search(raw_line)
            if match:
                payload["source"] = payload["source"] or "nca"
                payload["external_assistant_id"] = match.group("assistant_id")
                payload["assistant_id"] = payload["assistant_id"] or match.group("assistant_id")
                payload["configuration_provider_url"] = match.group("url")
                payload["application_id"] = match.group("application_id")
                payload["solution"] = payload["solution"] or match.group("solution")
                payload["group_tag"] = payload["group_tag"] or match.group("group_tag")
        if payload["tool_count"] == 0:
            match = TOOL_RETRIEVED_PATTERN.search(raw_line)
            if match:
                payload["tool_count"] = int(match.group(3))
        if "FFS flag evaluation:" in raw_line:
            flag_match = re.search(r"flagId=([^,]+), value=(.+?), elapsed=\d+ms", raw_line)
            if flag_match:
                payload["nca_flag_evaluations"][flag_match.group(1)] = flag_match.group(2)

    for raw_line in assistant_runtime_log.read_text(encoding="utf-8").splitlines() if assistant_runtime_log.exists() else []:
        if not payload["feature_flags"]:
            match = CALCULATED_FLAGS_PATTERN.search(raw_line)
            if match:
                parsed = _safe_json_from_match(match.group(1))
                if isinstance(parsed, dict):
                    payload["source"] = payload["source"] or "assistant_runtime"
                    payload["feature_flags"] = _flatten_feature_flags(parsed)
                    payload["solution"] = payload["solution"] or payload["feature_flags"].get("solution")
                    payload["group_tag"] = payload["group_tag"] or payload["feature_flags"].get("model_group_tag")
        if not payload["tool_names"] and ("Received init:" in raw_line or 'AgentCompletionResponse:' in raw_line and '"oneofKind":"init"' in raw_line):
            match = RECEIVED_INIT_PATTERN.search(raw_line) or AGENT_INIT_PATTERN.search(raw_line)
            if match:
                parsed = _safe_json_from_match(match.group(1))
                if isinstance(parsed, dict):
                    if "payload" in parsed:
                        info = parsed.get("payload", {}).get("init", {}).get("info", {})
                        context = parsed.get("context", {})
                    else:
                        info = parsed.get("info", {})
                        context = {}
                    metadata = _safe_json_from_match(info.get("metadata"))
                    payload["assistant_id"] = payload["assistant_id"] or context.get("assistantId")
                    payload["languages"] = info.get("languages") or payload["languages"]
                    payload["website"] = info.get("website") or payload["website"]
                    tool_definitions = info.get("toolDefinitions") or []
                    payload["tool_names"] = [item.get("name") for item in tool_definitions if isinstance(item, dict) and item.get("name")]
                    payload["tool_count"] = payload["tool_count"] or len(payload["tool_names"])
                    if isinstance(metadata, dict):
                        feature_flags = metadata.get("featureFlags", {})
                        if isinstance(feature_flags, dict):
                            payload["solution"] = payload["solution"] or feature_flags.get("solution")
                            payload["group_tag"] = payload["group_tag"] or feature_flags.get("groupTag")
        if payload["voice_id"] is None and "Nova Conversation is created:" in raw_line:
            parsed = _extract_first_json_object(raw_line)
            if isinstance(parsed, dict):
                payload["voice_id"] = parsed.get("voiceId")
                payload["languages"] = parsed.get("supportedLocales") or payload["languages"]

    payload["tool_names"] = _ordered_unique(payload["tool_names"])
    payload["languages"] = _ordered_unique(payload["languages"])
    return payload


def _parse_correlation_ids(session_dir: Path, start_conversation: Dict[str, Any], assistant_config: Dict[str, Any]) -> Dict[str, Any]:
    summary = _safe_load_json(session_dir / "summary.json")
    assistant_runtime_log = session_dir / "assistant_runtime_message.log"

    ids: Dict[str, Any] = {
        "session_id": summary.get("session_id"),
        "conversation_id": summary.get("conversation_id"),
        "account_id": start_conversation.get("account_id"),
        "assistant_id": assistant_config.get("assistant_id"),
        "external_assistant_id": assistant_config.get("external_assistant_id"),
        "start_conversation_request_id": start_conversation.get("request_id"),
        "srs_session_id": summary.get("srs_session_id"),
        "sgs_session_id": summary.get("sgs_session_id"),
        "speech_recognition_request_id": None,
        "speech_generation_request_id": None,
        "init_completion_id": None,
        "greeting_completion_id": None,
    }

    if assistant_runtime_log.exists():
        for raw_line in assistant_runtime_log.read_text(encoding="utf-8").splitlines():
            if ids["account_id"] is None:
                match = CONTEXT_FIELDS_PATTERN.search(raw_line)
                if match:
                    ids["account_id"] = int(match.group("account_id"))
                    ids["assistant_id"] = ids["assistant_id"] or match.group("assistant_id")
                    ids["conversation_id"] = ids["conversation_id"] or match.group("conversation_id")
            if ids["speech_recognition_request_id"] is None:
                match = SPEECH_RECOGNITION_STARTED_PATTERN.search(raw_line)
                if match:
                    parsed = _safe_json_from_match(match.group(1))
                    if isinstance(parsed, dict):
                        ids["speech_recognition_request_id"] = parsed.get("id")
            if ids["speech_generation_request_id"] is None:
                match = SPEECH_GENERATION_STARTED_PATTERN.search(raw_line)
                if match:
                    parsed = _safe_json_from_match(match.group(1))
                    if isinstance(parsed, dict):
                        ids["speech_generation_request_id"] = parsed.get("id")
            if ids["init_completion_id"] is None and "Sending init request" in raw_line:
                parsed = _extract_first_json_object(raw_line)
                if isinstance(parsed, dict):
                    ids["init_completion_id"] = parsed.get("completionId")
            if ids["greeting_completion_id"] is None and "Sending request" in raw_line and '"oneofKind":"generate"' in raw_line:
                parsed = _extract_first_json_object(raw_line)
                if isinstance(parsed, dict):
                    ids["greeting_completion_id"] = parsed.get("completionId")

    return ids


def _parse_session_outcome(session_dir: Path) -> Dict[str, Any]:
    assistant_runtime_log = session_dir / "assistant_runtime_message.log"
    payload: Dict[str, Any] = {
        "end_reason": None,
        "end_timestamp": None,
        "close_event": None,
        "source": None,
    }
    if not assistant_runtime_log.exists():
        return payload

    for raw_line in assistant_runtime_log.read_text(encoding="utf-8").splitlines():
        ts, body = _line_parts(raw_line)
        if payload["end_reason"] is None:
            match = CONVERSATION_END_REQUEST_PATTERN.search(raw_line)
            if match:
                payload["end_reason"] = match.group("reason")
                payload["end_timestamp"] = ts
                payload["source"] = "assistant_runtime"
                continue
        if payload["end_reason"] is None:
            match = PATCH_CONVERSATION_ENDED_PATTERN.search(raw_line)
            if match:
                payload["end_reason"] = match.group("reason")
                payload["end_timestamp"] = ts
                payload["source"] = "assistant_runtime"
                continue
        if payload["close_event"] is None and "Conversation close by event:" in raw_line:
            payload["close_event"] = _shorten(body)

    return payload


def _build_component_coverage(trace_summary: Dict[str, Any]) -> Dict[str, Any]:
    component_counts = trace_summary.get("summary", {}) if isinstance(trace_summary, dict) else {}
    expected_components = ("assistant_runtime", "agent_service", "nca", "cprc_srs", "cprc_sgs", "aig", "gmg")
    counts = {component: int(component_counts.get(component, 0) or 0) for component in expected_components}
    present_components = [component for component, count in counts.items() if count > 0]
    missing_components = [component for component, count in counts.items() if count == 0]
    core_components = ("assistant_runtime", "nca", "cprc_srs", "cprc_sgs")
    present_core = sum(1 for component in core_components if counts.get(component, 0) > 0)
    if present_core == len(core_components):
        trace_completeness = "high"
    elif present_core >= 2 and counts.get("assistant_runtime", 0) > 0:
        trace_completeness = "medium"
    else:
        trace_completeness = "low"
    return {
        "counts": counts,
        "present_components": present_components,
        "missing_components": missing_components,
        "trace_completeness": trace_completeness,
    }


def _build_key_timeline(
    start_conversation: Dict[str, Any],
    speech: Dict[str, Any],
    turns: List[Dict[str, Any]],
    session_outcome: Dict[str, Any],
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []

    def add(timestamp: Any, event: str, detail: str) -> None:
        if not timestamp:
            return
        entries.append({"timestamp": timestamp, "event": event, "detail": detail})

    add(
        start_conversation.get("started_at"),
        "nova_start_requested",
        f"request_id={start_conversation.get('request_id') or 'N/A'}",
    )
    add(
        start_conversation.get("completed_at"),
        "nova_start_completed",
        f"status={start_conversation.get('status') or 'unknown'} duration={_fmt_ms(start_conversation.get('duration_ms'))}",
    )

    srs = speech.get("srs", {})
    sgs = speech.get("sgs", {})
    add(srs.get("first_seen"), "srs_first_seen", f"linked={'yes' if srs.get('linked') else 'no'}")
    add(sgs.get("first_seen"), "sgs_first_seen", f"linked={'yes' if sgs.get('linked') else 'no'}")

    for turn in turns:
        add(
            turn.get("start_timestamp"),
            f"turn_{turn.get('turn_number')}_start",
            turn.get("turn_type") or "unknown",
        )
        add(
            turn.get("end_timestamp"),
            f"turn_{turn.get('turn_number')}_end",
            f"{turn.get('turn_type') or 'unknown'} duration={_fmt_ms(turn.get('duration_ms'))}",
        )

    add(sgs.get("last_audio_end"), "sgs_last_audio_end", "last synthesized audio end")
    add(
        session_outcome.get("end_timestamp"),
        "conversation_end",
        f"reason={session_outcome.get('end_reason') or 'unknown'}",
    )

    entries.sort(key=lambda item: item["timestamp"])
    return entries


def _build_diagnostic_snapshot(
    *,
    total_turns: int,
    turns: List[Dict[str, Any]],
    tool_call_count: int,
    component_coverage: Dict[str, Any],
    session_outcome: Dict[str, Any],
) -> Dict[str, Any]:
    contradictions = sum(len(turn.get("contradictions", [])) for turn in turns)
    failed_tool_call_count = sum(
        1
        for turn in turns
        for call in turn.get("tool_calls", [])
        if call.get("status") == "failed"
    )
    error_anomalies = sum(
        1
        for turn in turns
        for anomaly in turn.get("anomalies", [])
        if anomaly.get("severity") == "error"
    )
    has_user_turns = any(_is_user_turn_type(turn.get("turn_type")) for turn in turns)
    first_turn = turns[0] if turns else {}
    session_shape = "unknown"
    if total_turns == 1 and first_turn.get("turn_type") == "greeting" and tool_call_count == 0:
        session_shape = "greeting_only"
    elif tool_call_count > 0:
        session_shape = "tooling_session"
    elif total_turns > 1:
        session_shape = "interactive"

    trace_completeness = component_coverage.get("trace_completeness", "low")
    if trace_completeness == "high":
        confidence = "high"
    elif trace_completeness == "medium":
        confidence = "medium"
    else:
        confidence = "low"

    missing_components = component_coverage.get("missing_components", [])
    top_signals: List[str] = []

    if session_shape == "greeting_only" and session_outcome.get("end_reason") == "CallerDropped":
        top_signals.append("Caller dropped during or immediately after greeting; the session never reached a user turn.")
    elif session_shape == "greeting_only":
        top_signals.append("Greeting completed, but no user turn was captured in the traced session.")

    if tool_call_count == 0:
        top_signals.append("No logical tool calls were observed in the traced turns.")
    if contradictions:
        top_signals.append(f"{contradictions} contradiction signal(s) were detected between tool results and final answers.")
    if error_anomalies:
        top_signals.append(f"{error_anomalies} error-level anomaly/anomalies were surfaced in turn diagnostics.")
    if missing_components:
        top_signals.append(f"Trace is missing component coverage for: {', '.join(missing_components)}.")

    if not top_signals:
        top_signals.append("No high-signal failure or contradiction was detected in the current trace.")

    if contradictions or error_anomalies:
        diagnostic_status = "issue_detected"
    elif session_shape == "greeting_only" and session_outcome.get("end_reason") == "CallerDropped":
        diagnostic_status = "short_call"
    elif trace_completeness == "low":
        diagnostic_status = "trace_incomplete"
    else:
        diagnostic_status = "no_critical_issue_observed"

    key_facts = [
        f"Trace completeness: {trace_completeness}",
        f"User turns observed: {'yes' if has_user_turns else 'no'}",
        f"Tool calls observed: {tool_call_count}",
        f"Contradiction signals: {contradictions}",
        f"Error anomalies: {error_anomalies}",
        f"Session outcome: {session_outcome.get('end_reason') or 'unknown'}",
    ]

    return {
        "diagnostic_status": diagnostic_status,
        "confidence": confidence,
        "session_shape": session_shape,
        "trace_completeness": trace_completeness,
        "total_turns": total_turns,
        "tool_call_count": tool_call_count,
        "contradiction_count": contradictions,
        "error_anomaly_count": error_anomalies,
        "failed_tool_call_count": failed_tool_call_count,
        "has_user_turns": has_user_turns,
        "missing_components": missing_components,
        "session_outcome_reason": session_outcome.get("end_reason"),
        "top_signals": top_signals,
        "key_facts": key_facts,
    }


def _build_basic_judgment(
    *,
    reported_symptom: str | None,
    diagnostic_snapshot: Dict[str, Any],
    start_conversation: Dict[str, Any],
    component_coverage: Dict[str, Any],
    speech: Dict[str, Any],
    turns: List[Dict[str, Any]],
    session_outcome: Dict[str, Any],
) -> Dict[str, Any]:
    contradiction_count = sum(len(turn.get("contradictions", [])) for turn in turns)
    failed_tool_calls = [
        call
        for turn in turns
        for call in turn.get("tool_calls", [])
        if call.get("status") == "failed"
    ]
    user_turns = [turn for turn in turns if _is_user_turn_type(turn.get("turn_type"))]
    total_error_anomalies = sum(
        1
        for turn in turns
        for anomaly in turn.get("anomalies", [])
        if anomaly.get("severity") == "error"
    )
    trace_completeness = diagnostic_snapshot.get("trace_completeness") or component_coverage.get("trace_completeness", "low")
    diagnostic_status = diagnostic_snapshot.get("diagnostic_status") or "unknown"
    confidence = diagnostic_snapshot.get("confidence") or "unknown"

    outcome_category = "investigation_required"
    owner = "unknown"
    severity = "medium"
    customer_impact = "Needs manual review to determine user-visible impact."

    if contradiction_count:
        outcome_category = "answer_contradiction"
        owner = "assistant_runtime"
        severity = "high"
        customer_impact = "AIR likely answered inconsistently with tool output."
    elif failed_tool_calls:
        outcome_category = "tool_failure"
        owner = "nca_or_tool_backend"
        severity = "high"
        customer_impact = "A required tool failed during the conversation."
    elif diagnostic_status == "short_call":
        outcome_category = "short_call"
        owner = "caller_or_call_flow"
        severity = "low"
        customer_impact = "The conversation ended before AIR could handle a real request."
    elif trace_completeness == "low":
        outcome_category = "incomplete_trace"
        owner = "logtracer_or_time_window"
        severity = "medium"
        customer_impact = "The trace is incomplete, so root cause cannot be confirmed yet."
    elif total_error_anomalies:
        outcome_category = "orchestration_gap"
        owner = "assistant_runtime_or_nca"
        severity = "medium"
        customer_impact = "The session completed with execution anomalies that may affect behavior."
    elif diagnostic_status == "no_critical_issue_observed":
        outcome_category = "no_issue_observed"
        owner = "unknown"
        severity = "info"
        customer_impact = "No clear customer-facing defect was confirmed in this trace."

    symptom_assessment = "not_evaluated"
    normalized_reported_symptom = (reported_symptom or "").strip()
    if normalized_reported_symptom:
        if outcome_category in {"answer_contradiction", "tool_failure"}:
            symptom_assessment = "confirmed"
        elif outcome_category in {"short_call", "incomplete_trace", "investigation_required"}:
            symptom_assessment = "not_confirmed"
        else:
            symptom_assessment = "partially_confirmed"

    actionable_now = outcome_category not in {"no_issue_observed"}
    if outcome_category == "short_call" and not user_turns:
        actionable_now = True

    return {
        "outcome_category": outcome_category,
        "severity": severity,
        "owner": owner,
        "confidence": confidence,
        "customer_impact": customer_impact,
        "actionable_now": actionable_now,
        "diagnostic_status": diagnostic_status,
        "reported_symptom": normalized_reported_symptom or None,
        "symptom_assessment": symptom_assessment,
        "start_conversation_ok": start_conversation.get("status") == "success",
        "has_user_turns": bool(user_turns),
        "speech_linked": bool(speech.get("srs", {}).get("linked") and speech.get("sgs", {}).get("linked")),
    }


def _build_ai_diagnosis_report(
    *,
    diagnostic_snapshot: Dict[str, Any],
    basic_judgment: Dict[str, Any],
) -> Dict[str, Any]:
    outcome_category = basic_judgment.get("outcome_category") or "investigation_required"
    end_reason = diagnostic_snapshot.get("session_outcome_reason")
    if not end_reason:
        end_reason = diagnostic_snapshot.get("key_facts", [])[-1].split(": ", 1)[-1] if diagnostic_snapshot.get("key_facts") else None

    if outcome_category == "answer_contradiction":
        final_verdict = "AIR produced a final answer that likely contradicted successful tool output."
        summary = (
            "The trace contains contradiction evidence in an observed user turn, and the available component coverage "
            "is strong enough to treat this as a likely product issue rather than a logging gap."
        )
    elif outcome_category == "tool_failure":
        final_verdict = "A required tool failed during an observed user turn."
        summary = "The trace shows a tool-side failure during a real user request, so the session supports a product-side failure diagnosis."
    elif outcome_category == "short_call":
        final_verdict = (
            f"Short call: the session ended with `{end_reason or 'unknown'}` before AIR handled a user turn."
        )
        summary = (
            "The trace shows a short call that ended before AIR handled a real user request, so this session does not "
            "support diagnosing answer quality or KB usage."
        )
    elif outcome_category == "incomplete_trace":
        final_verdict = "Trace completeness is too low to make a confident root-cause call."
        summary = "The available logs are too incomplete for a confident product diagnosis."
    elif outcome_category == "orchestration_gap":
        final_verdict = "Execution anomalies were observed, but the trace does not yet prove a direct answer contradiction."
        summary = "The trace contains execution anomalies that could affect behavior, but the evidence is not yet specific enough to name a single product fault."
    elif outcome_category == "no_issue_observed":
        final_verdict = "No high-signal defect was observed in the available trace evidence."
        summary = "The available trace does not show a clear customer-facing defect."
    else:
        final_verdict = "The trace needs manual review before a confident diagnosis can be made."
        summary = "The available evidence is mixed, so the report stops at a cautious preliminary diagnosis."

    evidence = _ordered_unique(
        list(diagnostic_snapshot.get("top_signals", [])) + list(diagnostic_snapshot.get("key_facts", [])[:3])
    )

    missing_components = diagnostic_snapshot.get("missing_components", [])
    gaps: List[str] = []
    major_gap_components = [
        component for component in missing_components if component in {"assistant_runtime", "agent_service", "nca", "cprc_srs", "cprc_sgs"}
    ]
    if major_gap_components:
        gaps.append(f"Missing component coverage: {', '.join(major_gap_components)}.")
    if diagnostic_snapshot.get("trace_completeness") == "low":
        gaps.append("Trace completeness is low, so cross-component conclusions should be treated as partial.")
    if not gaps:
        gaps.append("No major evidence gaps were detected in the available trace.")

    next_actions: List[str] = []
    if outcome_category == "answer_contradiction":
        next_actions.append(
            "Inspect the affected turns with toolcall_audit or the turn report to confirm whether AIR ignored or contradicted tool output."
        )
    if outcome_category == "tool_failure":
        next_actions.append("Review the failed tool call and the corresponding backend component logs before assigning root cause.")
    if outcome_category == "short_call":
        next_actions.append("Use a multi-turn or tool-using session if the goal is to validate AIR reasoning, KB usage, or tool behavior.")
    if outcome_category == "incomplete_trace":
        next_actions.append("Rerun the trace with a broader time window or by conversationId to recover missing component logs.")
    if diagnostic_snapshot.get("error_anomaly_count", 0):
        next_actions.append("Review the first error-level anomaly and its surrounding component logs before concluding root cause.")
    if "agent_service" in missing_components:
        next_actions.append(
            "If assistant config or tool orchestration details matter, rerun with a broader time window or trace by conversationId to try to recover agent_service logs."
        )
    if any(component in missing_components for component in ("nca", "cprc_srs", "cprc_sgs")):
        next_actions.append("Treat speech or Nova lifecycle conclusions as partial until the missing core components are present.")
    if not next_actions:
        next_actions.append("If the user reported a product issue, choose a more representative session or expand the time window before declaring it healthy.")

    return {
        "final_verdict": final_verdict,
        "summary": summary,
        "evidence": evidence,
        "gaps": gaps,
        "next_actions": _ordered_unique(next_actions),
    }


def _build_executive_summary(
    *,
    total_turns: int,
    turns: List[Dict[str, Any]],
    tool_call_count: int,
    component_coverage: Dict[str, Any],
    session_outcome: Dict[str, Any],
) -> Dict[str, Any]:
    return _build_diagnostic_snapshot(
        total_turns=total_turns,
        turns=turns,
        tool_call_count=tool_call_count,
        component_coverage=component_coverage,
        session_outcome=session_outcome,
    )


def _build_triage(
    *,
    reported_symptom: str | None,
    executive_summary: Dict[str, Any],
    start_conversation: Dict[str, Any],
    component_coverage: Dict[str, Any],
    speech: Dict[str, Any],
    turns: List[Dict[str, Any]],
    session_outcome: Dict[str, Any],
) -> Dict[str, Any]:
    judgment = _build_basic_judgment(
        reported_symptom=reported_symptom,
        diagnostic_snapshot=executive_summary,
        start_conversation=start_conversation,
        component_coverage=component_coverage,
        speech=speech,
        turns=turns,
        session_outcome=session_outcome,
    )
    ai_report = _build_ai_diagnosis_report(
        diagnostic_snapshot=executive_summary,
        basic_judgment=judgment,
    )
    return {
        **judgment,
        "final_verdict": ai_report["final_verdict"],
        "symptom_evidence": ai_report["evidence"],
    }


def _build_session_diagnostic(session_dir: Path, reported_symptom: str | None = None) -> Dict[str, Any]:
    session_summary = toolcall_audit.summarize_session(session_dir)
    trace_summary = _safe_load_json(session_dir / "summary.json")
    srs_session_id = trace_summary.get("srs_session_id")
    sgs_session_id = trace_summary.get("sgs_session_id")
    assistant_runtime_log = session_dir / "assistant_runtime_message.log"
    nca_log = session_dir / "nca_message.log"
    start_conversation = _parse_start_conversation(assistant_runtime_log)
    assistant_configuration = _parse_assistant_configuration(session_dir)
    correlation_ids = _parse_correlation_ids(session_dir, start_conversation, assistant_configuration)
    session_outcome = _parse_session_outcome(session_dir)
    component_coverage = _build_component_coverage(trace_summary)
    speech = {
        "srs": _parse_srs_log(session_dir / "cprc_srs_message.log", srs_session_id),
        "sgs": _parse_sgs_log(session_dir / "cprc_sgs_message.log", sgs_session_id),
    }
    assistant_runtime_latency = _parse_assistant_runtime_latency(assistant_runtime_log)
    nca_latency = _parse_nca_latency(nca_log)
    turns = session_summary.get("turns", [])
    diagnostic_snapshot = _build_diagnostic_snapshot(
        total_turns=session_summary.get("total_turns", 0),
        turns=turns,
        tool_call_count=session_summary.get("tool_call_count", 0),
        component_coverage=component_coverage,
        session_outcome=session_outcome,
    )
    basic_judgment = _build_basic_judgment(
        reported_symptom=reported_symptom,
        diagnostic_snapshot=diagnostic_snapshot,
        start_conversation=start_conversation,
        component_coverage=component_coverage,
        speech=speech,
        turns=turns,
        session_outcome=session_outcome,
    )
    ai_diagnosis_report = _build_ai_diagnosis_report(
        diagnostic_snapshot=diagnostic_snapshot,
        basic_judgment=basic_judgment,
    )
    key_timeline = _build_key_timeline(start_conversation, speech, turns, session_outcome)
    latency_path = _detect_latency_path(
        start_conversation=start_conversation,
        assistant_configuration=assistant_configuration,
        component_coverage=component_coverage,
    )
    latency_segments = _build_latency_segments(
        latency_path=latency_path,
        speech=speech,
        turns=turns,
        component_coverage=component_coverage,
    )
    latency_buckets = _build_latency_buckets(latency_segments)
    manual_rca_view = _build_manual_rca_view(
        speech=speech,
        assistant_runtime_latency=assistant_runtime_latency,
        nca_latency=nca_latency,
        turns=turns,
    )
    layer_diagnostics = _build_layer_diagnostics(
        component_coverage=component_coverage,
        speech=speech,
        assistant_runtime_latency=assistant_runtime_latency,
        nca_latency=nca_latency,
        turns=turns,
        manual_rca_view=manual_rca_view,
    )
    turn_summary_matrix = _build_turn_summary_matrix(
        turns=turns,
        manual_rca_view=manual_rca_view,
    )
    session_scorecard = _build_session_scorecard(
        session_id=session_summary.get("session_id"),
        latency_path=latency_path,
        basic_judgment=basic_judgment,
        component_coverage=component_coverage,
        turn_summary_matrix=turn_summary_matrix,
    )
    action_summary = _build_action_summary(
        session_scorecard=session_scorecard,
        turn_summary_matrix=turn_summary_matrix,
        component_coverage=component_coverage,
    )
    expanded_timelines = _build_expanded_timelines(
        turns=turns,
        turn_summary_matrix=turn_summary_matrix,
        manual_rca_view=manual_rca_view,
    )
    evidence_registry = _build_evidence_registry(
        turn_summary_matrix=turn_summary_matrix,
        layer_diagnostics=layer_diagnostics,
    )

    return {
        "session_dir": str(session_dir),
        "session_id": session_summary.get("session_id"),
        "conversation_id": session_summary.get("conversation_id"),
        "total_turns": session_summary.get("total_turns"),
        "turns_with_tools": session_summary.get("turns_with_tools"),
        "tool_call_count": session_summary.get("tool_call_count"),
        "srs_session_id": srs_session_id,
        "sgs_session_id": sgs_session_id,
        "start_conversation": start_conversation,
        "session_outcome": session_outcome,
        "assistant_configuration": assistant_configuration,
        "correlation_ids": correlation_ids,
        "component_coverage": component_coverage,
        "latency_path": latency_path,
        "latency_segments": latency_segments,
        "latency_buckets": latency_buckets,
        "manual_rca_view": manual_rca_view,
        "layer_diagnostics": layer_diagnostics,
        "session_scorecard": session_scorecard,
        "action_summary": action_summary,
        "turn_summary_matrix": turn_summary_matrix,
        "expanded_timelines": expanded_timelines,
        "evidence_registry": evidence_registry,
        "diagnostic_snapshot": diagnostic_snapshot,
        "basic_judgment": basic_judgment,
        "ai_diagnosis_report": ai_diagnosis_report,
        "key_timeline": key_timeline,
        "speech": speech,
        "turns": turns,
    }


def _aggregate(payload_sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
    contradiction_counter: Dict[str, int] = {}
    speech_disconnects = 0
    for session in payload_sessions:
        for turn in session["turns"]:
            for contradiction in turn.get("contradictions", []):
                key = contradiction.get("type") or "unknown"
                contradiction_counter[key] = contradiction_counter.get(key, 0) + 1
        speech_disconnects += len(session["speech"]["srs"]["disconnect_events"])
        speech_disconnects += len(session["speech"]["sgs"]["disconnect_events"])

    return {
        "contradictions": contradiction_counter,
        "speech_disconnect_events": speech_disconnects,
    }


ZH_EXACT_TRANSLATIONS = {
    "No contradiction signals": "未检测到 contradiction signals",
    "No final verdict extracted.": "未提取到最终结论。",
    "No AI diagnosis summary generated.": "未生成 AI 诊断摘要。",
    "no evidence synthesized": "未生成证据摘要",
    "none recorded": "无",
    "No timeline events extracted": "未提取到时间线事件",
    "No latency segments extracted": "未提取到 latency segments",
    "Caller dropped during or immediately after greeting; the session never reached a user turn.": "Caller 在 greeting 期间或刚结束后就挂断了；该会话没有进入用户 turn。",
    "Greeting completed, but no user turn was captured in the traced session.": "Greeting 已完成，但当前 trace 中没有捕获到用户 turn。",
    "No logical tool calls were observed in the traced turns.": "在已追踪的 turns 中未观察到 logical tool calls。",
    "No high-signal failure or contradiction was detected in the current trace.": "当前 trace 中未检测到高信号故障或 contradiction。",
    "No major evidence gaps were detected in the available trace.": "当前可用 trace 中未检测到主要证据缺口。",
    "The conversation ended before AIR could handle a real request.": "会话在 AIR 处理真实请求前就结束了。",
    "AIR likely answered inconsistently with tool output.": "AIR 很可能给出了与 tool output 不一致的回答。",
    "A required tool failed during the conversation.": "会话中一个必需的 tool 调用失败。",
    "Needs manual review to determine user-visible impact.": "需要人工复核以判断用户可感知影响。",
    "The trace is incomplete, so root cause cannot be confirmed yet.": "当前 trace 不完整，暂时无法确认 root cause。",
    "The session completed with execution anomalies that may affect behavior.": "该会话存在可能影响行为的执行异常。",
    "No clear customer-facing defect was confirmed in this trace.": "当前 trace 未确认明确的用户侧缺陷。",
    "AIR produced a final answer that likely contradicted successful tool output.": "AIR 最终回答很可能与成功的 tool output 相矛盾。",
    "A required tool failed during an observed user turn.": "在一个已观察到的 user turn 中，必需的 tool 调用失败。",
    "Trace completeness is too low to make a confident root-cause call.": "Trace completeness 过低，无法做出有把握的 root-cause 判断。",
    "Execution anomalies were observed, but the trace does not yet prove a direct answer contradiction.": "观察到了执行异常，但当前 trace 还不足以证明存在直接的回答矛盾。",
    "No high-signal defect was observed in the available trace evidence.": "当前可用 trace evidence 中未观察到高信号缺陷。",
    "The trace needs manual review before a confident diagnosis can be made.": "需要人工复核该 trace 后，才能做出有把握的诊断。",
    "The trace contains contradiction evidence in an observed user turn, and the available component coverage is strong enough to treat this as a likely product issue rather than a logging gap.": "该 trace 在一个已观察到的 user turn 中包含 contradiction evidence，且 component coverage 足够完整，因此更像真实产品问题而不是日志缺口。",
    "The trace shows a tool-side failure during a real user request, so the session supports a product-side failure diagnosis.": "该 trace 显示在真实用户请求期间发生了 tool 侧失败，因此支持产品侧故障判断。",
    "The trace shows a short call that ended before AIR handled a real user request, so this session does not support diagnosing answer quality or KB usage.": "该 trace 显示这是一次短通话，会话在 AIR 处理真实用户请求前就结束，因此不支持用它诊断 answer quality 或 KB usage。",
    "The available logs are too incomplete for a confident product diagnosis.": "当前日志过于不完整，无法做出有把握的产品诊断。",
    "The trace contains execution anomalies that could affect behavior, but the evidence is not yet specific enough to name a single product fault.": "该 trace 包含可能影响行为的执行异常，但证据还不够具体，无法明确指向单一产品故障。",
    "The available trace does not show a clear customer-facing defect.": "当前 trace 未显示明确的用户侧缺陷。",
    "The available evidence is mixed, so the report stops at a cautious preliminary diagnosis.": "当前证据混杂，因此报告只给出谨慎的初步诊断。",
    "Inspect the affected turns with toolcall_audit or the turn report to confirm whether AIR ignored or contradicted tool output.": "使用 toolcall_audit 或 turn report 检查受影响的 turns，确认 AIR 是否忽略了 tool output 或与之矛盾。",
    "Review the failed tool call and the corresponding backend component logs before assigning root cause.": "在归因 root cause 前，先检查失败的 tool call 及对应 backend component logs。",
    "Use a multi-turn or tool-using session if the goal is to validate AIR reasoning, KB usage, or tool behavior.": "如果目标是验证 AIR reasoning、KB usage 或 tool behavior，请改用 multi-turn 或含 tool 调用的 session。",
    "Rerun the trace with a broader time window or by conversationId to recover missing component logs.": "使用更大的时间窗口或改按 conversationId 重跑 trace，以补回缺失的 component logs。",
    "Review the first error-level anomaly and its surrounding component logs before concluding root cause.": "在得出 root cause 结论前，先检查第一个 error-level anomaly 及其周边 component logs。",
    "If assistant config or tool orchestration details matter, rerun with a broader time window or trace by conversationId to try to recover agent_service logs.": "如果 assistant config 或 tool orchestration 细节很重要，请扩大时间窗口，或按 conversationId 重跑 trace，以尝试补回 agent_service logs。",
    "Treat speech or Nova lifecycle conclusions as partial until the missing core components are present.": "在缺失的核心组件补齐前，speech 或 Nova lifecycle 的结论都应视为部分结论。",
    "If the user reported a product issue, choose a more representative session or expand the time window before declaring it healthy.": "如果用户反馈了产品问题，在判定它健康之前，请选择更有代表性的 session 或扩大时间窗口。",
    "Client disconnected": "客户端断开连接",
    "playback interrupted": "播放被打断",
}

ZH_REGEX_TRANSLATIONS = (
    (re.compile(r"^(\d+) contradiction signal\(s\) were detected between tool results and final answers\.$"), r"检测到 \1 个 tool result 与最终回答之间的 contradiction signal。"),
    (re.compile(r"^(\d+) error-level anomaly/anomalies were surfaced in turn diagnostics\.$"), r"在 turn diagnostics 中发现 \1 个 error-level anomaly。"),
    (re.compile(r"^Trace is missing component coverage for: (.+)\.$"), r"Trace 缺少这些组件覆盖：\1。"),
    (re.compile(r"^Tool failure detected: `([^`]+)` ended with status `([^`]+)`\.$"), r"检测到 tool failure：`\1` 最终状态为 `\2`。"),
    (re.compile(r"^Short call: the session ended with `([^`]+)` before AIR handled a user turn\.$"), r"短通话：会话在 AIR 处理用户 turn 前以 `\1` 结束。"),
    (re.compile(r"^Missing component coverage: (.+)\.$"), r"缺少这些组件覆盖：\1。"),
    (re.compile(r"^Trace completeness: ([A-Za-z_]+)$"), r"Trace 完整度: \1"),
    (re.compile(r"^User turns observed: ([A-Za-z_]+)$"), r"是否观察到用户 turns: \1"),
    (re.compile(r"^Tool calls observed: (\d+)$"), r"观察到的 Tool calls: \1"),
    (re.compile(r"^Contradiction signals: (\d+)$"), r"Contradiction signals 数量: \1"),
    (re.compile(r"^Error anomalies: (\d+)$"), r"Error anomalies 数量: \1"),
    (re.compile(r"^Session outcome: ([A-Za-z_]+)$"), r"会话结果: \1"),
)

ZH_MARKDOWN_REPLACEMENTS = (
    ("# IVA Diagnostic Report", "# IVA 诊断报告"),
    ("## Aggregate Signals", "## 聚合信号"),
    ("## Session `", "## 会话 `"),
    ("### Final Verdict", "### 最终结论"),
    ("### Action Summary", "### 行动摘要"),
    ("### Diagnostic Snapshot", "### 诊断快照"),
    ("### Session Scorecard", "### 会话评分卡"),
    ("### Turn Summary Matrix", "### Turn 摘要矩阵"),
    ("### Expanded Timelines", "### 展开时间线"),
    ("### Evidence / Blind Spots", "### 证据 / 盲区"),
    ("### Basic Judgment", "### 基础判断"),
    ("### AI Diagnosis Report", "### AI 诊断报告"),
    ("### Component Coverage", "### 组件覆盖"),
    ("### Nova / Start Conversation", "### Nova / Start Conversation"),
    ("### Session Outcome", "### 会话结果"),
    ("### Assistant Configuration", "### Assistant Configuration"),
    ("### Correlation IDs", "### Correlation IDs"),
    ("### Latency Executive View", "### Latency Executive View"),
    ("### Latency Segments", "### Latency Segments"),
    ("### Manual RCA View", "### Manual RCA View"),
    ("### Layer Diagnostics", "### Layer Diagnostics"),
    ("### Key Timeline", "### 关键时间线"),
    ("### Speech Linkage", "### Speech Linkage"),
    ("### Turn Diagnostics", "### Turn Diagnostics"),
    ("### Recommended Next Actions", "### 建议的下一步"),
    ("- Sessions: ", "- 会话数: "),
    ("- Tool calls: ", "- Tool 调用数: "),
    ("- Speech disconnect signals: ", "- Speech 断连信号数: "),
    ("- Contradiction `", "- Contradiction `"),
    ("- Conversation: ", "- Conversation ID: "),
    ("- Trace dir: ", "- Trace 目录: "),
    ("- Turns: ", "- Turns 数: "),
    ("- Turns with tools: ", "- 含 Tool 的 Turns 数: "),
    ("- Status: ", "- 状态: "),
    ("- Session shape: ", "- 会话形态: "),
    ("- Trace completeness: ", "- Trace 完整度: "),
    ("- User turns observed: ", "- 是否观察到用户 turns: "),
    ("- Tool calls observed: ", "- 观察到的 Tool calls: "),
    ("- Contradiction signals: ", "- Contradiction signals 数量: "),
    ("- Error anomalies: ", "- Error anomalies 数量: "),
    ("- Fact: ", "- 事实: "),
    ("- Signal: ", "- 信号: "),
    ("- Diagnostic status: ", "- 诊断状态: "),
    ("- Outcome category: ", "- 结论类别: "),
    ("- Severity: ", "- 严重程度: "),
    ("- Owner: ", "- Owner: "),
    ("- Confidence: ", "- 置信度: "),
    ("- Customer impact: ", "- 用户影响: "),
    ("- Actionable now: ", "- 当前可执行: "),
    ("- Reported symptom: ", "- 上报问题: "),
    ("- Assessment: ", "- 判断: "),
    ("- Summary: ", "- 摘要: "),
    ("- Evidence: ", "- 证据: "),
    ("- Gap: ", "- 缺口: "),
    ("- Missing components: ", "- 缺失组件: "),
    ("- Nova path: ", "- Nova 路径: "),
    ("- Request ID: ", "- Request ID: "),
    ("- Timing: ", "- 时序: "),
    ("- Account ID: ", "- Account ID: "),
    ("- Conversation ID: ", "- Conversation ID: "),
    ("- Assistant ID: ", "- Assistant ID: "),
    ("- gRPC address: ", "- gRPC 地址: "),
    ("- End reason: ", "- End reason: "),
    ("- End timestamp: ", "- 结束时间: "),
    ("- Close event: ", "- Close event: "),
    ("- Source: ", "- 来源: "),
    ("- External assistant ID: ", "- External assistant ID: "),
    ("- Config provider: ", "- Config provider: "),
    ("- Application ID: ", "- Application ID: "),
    ("- Solution / groupTag: ", "- Solution / groupTag: "),
    ("- Voice ID: ", "- Voice ID: "),
    ("- Languages: ", "- Languages: "),
    ("- Website: ", "- Website: "),
    ("- Tools (", "- Tools ("),
    ("- Enabled skills: ", "- Enabled skills: "),
    ("- Graph bundle: ", "- Graph bundle: "),
    ("- Graph skills: ", "- Graph skills: "),
    ("- Feature flags:", "- Feature flags:"),
    ("- Feature flags: none extracted", "- Feature flags: 未提取到"),
    ("- NCA flag evaluations:", "- NCA flag evaluations:"),
    ("- NCA flag evaluations: none extracted", "- NCA flag evaluations: 未提取到"),
    ("- No timeline events extracted", "- 未提取到时间线事件"),
    ("- Path: ", "- Path: "),
    ("- No latency segments extracted", "- 未提取到 latency segments"),
    ("| Component | Expected ID | Linked | First Seen | Last Seen | Disconnect Signals |", "| Component | Expected ID | Linked | First Seen | Last Seen | Disconnect Signals |"),
    ("- Observed IDs: ", "- 观察到的 IDs: "),
    ("- ASR latency: ", "- ASR latency: "),
    ("- IVA delivery latency: ", "- IVA delivery latency: "),
    ("- Disconnect / teardown:", "- Disconnect / teardown:"),
    ("- Disconnect / teardown: none detected", "- Disconnect / teardown: 未检测到"),
    ("- Generate requests: ", "- Generate requests: "),
    ("- Cancel requests: ", "- Cancel requests: "),
    ("- First chunk latency: ", "- First chunk latency: "),
    ("- Playback duration: ", "- Playback duration: "),
    ("- Last audio end: ", "- 最后一段音频结束时间: "),
    ("- Disconnect / interruption:", "- Disconnect / interruption:"),
    ("- Disconnect / interruption: none detected", "- Disconnect / interruption: 未检测到"),
    ("#### Turn ", "#### Turn "),
    ("- Latency: ", "- 延迟: "),
    ("- User: ", "- 用户: "),
    ("- AI: ", "- AI: "),
    ("- Tool calls:", "- Tool 调用:"),
    ("- Tool calls: none", "- Tool 调用: 无"),
    ("- Contradictions:", "- Contradictions:"),
    ("- Anomalies:", "- Anomalies:"),
)


def _translate_text_zh(text: str) -> str:
    translated = ZH_EXACT_TRANSLATIONS.get(text, text)
    for pattern, replacement in ZH_REGEX_TRANSLATIONS:
        translated = pattern.sub(replacement, translated)
    translated = re.sub(r"\byes\b", "是", translated)
    translated = re.sub(r"\bno\b", "否", translated)
    translated = re.sub(r"\bNone\b", "无", translated)
    translated = translated.replace(" log(s)", " 条 log")
    return translated


def _translate_outside_code_zh(text: str) -> str:
    parts = text.split("`")
    for index in range(0, len(parts), 2):
        parts[index] = _translate_text_zh(parts[index])
    return "`".join(parts)


def _translate_markdown_to_zh(markdown: str) -> str:
    translatable_prefixes = (
        "- 事实: ",
        "- 信号: ",
        "- 摘要: ",
        "- 证据: ",
        "- 缺口: ",
        "- 用户影响: ",
    )
    translated_lines: List[str] = []
    for line in markdown.splitlines():
        updated = line
        for src, dst in ZH_MARKDOWN_REPLACEMENTS:
            updated = updated.replace(src, dst)
        for prefix in translatable_prefixes:
            if updated.startswith(prefix):
                updated = prefix + _translate_text_zh(updated[len(prefix):])
                break
        else:
            if updated.startswith("- ") and not updated.startswith("- `"):
                updated = "- " + _translate_text_zh(updated[2:])
        updated = _translate_outside_code_zh(updated)
        translated_lines.append(updated)
    return "\n".join(translated_lines).rstrip() + "\n"


def _append_markdown_table(lines: List[str], headers: List[str], rows: List[List[str]]) -> None:
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")


def render_markdown(payload: Dict[str, Any], lang: str = "zh") -> str:
    lines = [
        "# IVA Diagnostic Report",
        "",
        f"- Sessions: {payload['session_count']}",
        f"- Tool calls: {payload['tool_call_count']}",
        f"- Speech disconnect signals: {payload['aggregate']['speech_disconnect_events']}",
        "",
    ]

    contradictions = payload["aggregate"]["contradictions"]
    lines.append("## Aggregate Signals")
    if contradictions:
        for key, value in contradictions.items():
            lines.append(f"- Contradiction `{key}`: {value}")
    else:
        lines.append("- No contradiction signals")

    for session in payload["sessions"]:
        lines.append("")
        lines.append(f"## Session `{session['session_id'] or 'unknown-session'}`")
        lines.append(f"- Conversation: `{session['conversation_id'] or 'N/A'}`")
        lines.append(f"- Trace dir: `{session['session_dir']}`")
        lines.append(f"- Turns: {session['total_turns']}")
        lines.append(f"- Turns with tools: {session['turns_with_tools']}")
        lines.append(f"- Tool calls: {session['tool_call_count']}")

        diagnostic_snapshot = session.get("diagnostic_snapshot") or {}
        basic_judgment = session.get("basic_judgment") or {}
        ai_diagnosis_report = session.get("ai_diagnosis_report") or {}
        turn_summary_matrix = session.get("turn_summary_matrix") or _build_turn_summary_matrix(
            turns=session.get("turns") or [],
            manual_rca_view=session.get("manual_rca_view") or {},
        )
        session_scorecard = session.get("session_scorecard") or _build_session_scorecard(
            session_id=session.get("session_id"),
            latency_path=session.get("latency_path") or "unknown",
            basic_judgment=basic_judgment,
            component_coverage=session.get("component_coverage") or {},
            turn_summary_matrix=turn_summary_matrix,
        )
        action_summary = session.get("action_summary") or _build_action_summary(
            session_scorecard=session_scorecard,
            turn_summary_matrix=turn_summary_matrix,
            component_coverage=session.get("component_coverage") or {},
        )
        expanded_timelines = session.get("expanded_timelines") or _build_expanded_timelines(
            turns=session.get("turns") or [],
            turn_summary_matrix=turn_summary_matrix,
            manual_rca_view=session.get("manual_rca_view") or {},
        )
        layer_diagnostics = session.get("layer_diagnostics") or []
        evidence_registry = session.get("evidence_registry") or _build_evidence_registry(
            turn_summary_matrix=turn_summary_matrix,
            layer_diagnostics=layer_diagnostics,
        )
        lines.append("")
        lines.append("### Action Summary")
        lines.append(f"- Customer impact: {action_summary.get('customer_impact') or 'unknown'}")
        if action_summary.get("worst_turn_number") is not None:
            lines.append(
                f"- Worst turn: `{action_summary.get('worst_turn_number')}` "
                f"(`{action_summary.get('worst_turn_transcript') or 'N/A'}`)"
            )
        lines.append(f"- Strongest claim: {action_summary.get('strongest_claim') or 'unknown'}")
        lines.append(f"- Likely owner: `{action_summary.get('likely_owner') or 'unknown'}`")
        lines.append(
            f"- Attribution confidence: `{action_summary.get('attribution_confidence') or 'unknown'}`"
        )
        lines.append(f"- Owner note: {action_summary.get('owner_note') or 'unknown'}")
        lines.append(f"- Next action: {action_summary.get('next_action') or 'unknown'}")

        lines.append("")
        lines.append("### Final Verdict")
        lines.append(f"- {ai_diagnosis_report.get('final_verdict') or 'No final verdict extracted.'}")

        lines.append("")
        lines.append("### Diagnostic Snapshot")
        lines.append(f"- Status: `{diagnostic_snapshot.get('diagnostic_status') or 'unknown'}`")
        lines.append(f"- Session shape: `{diagnostic_snapshot.get('session_shape') or 'unknown'}`")
        lines.append(f"- Trace completeness: `{diagnostic_snapshot.get('trace_completeness') or 'unknown'}`")
        lines.append(f"- User turns observed: `{'yes' if diagnostic_snapshot.get('has_user_turns') else 'no'}`")
        lines.append(f"- Tool calls observed: `{diagnostic_snapshot.get('tool_call_count', 0)}`")
        lines.append(f"- Contradiction signals: `{diagnostic_snapshot.get('contradiction_count', 0)}`")
        lines.append(f"- Error anomalies: `{diagnostic_snapshot.get('error_anomaly_count', 0)}`")
        for fact in diagnostic_snapshot.get("key_facts", []):
            lines.append(f"- Fact: {fact}")
        for signal in diagnostic_snapshot.get("top_signals", []):
            lines.append(f"- Signal: {signal}")

        lines.append("")
        lines.append("### Session Scorecard")
        _append_markdown_table(
            lines,
            headers=[
                "Session",
                "Path",
                "Verdict",
                "User-perceived slow?",
                "Primary bottleneck",
                "Likely owner",
                "Attribution confidence",
            ],
            rows=[
                [
                    f"`{session_scorecard.get('session_id') or 'unknown-session'}`",
                    f"`{session_scorecard.get('path') or 'unknown'}`",
                    f"`{session_scorecard.get('verdict') or 'unknown'}`",
                    "Yes" if session_scorecard.get("user_perceived_slow") else "No",
                    f"`{session_scorecard.get('primary_bottleneck') or 'none'}`",
                    f"`{session_scorecard.get('likely_owner') or session_scorecard.get('owner') or 'unknown'}`",
                    f"`{session_scorecard.get('attribution_confidence') or 'unknown'}`",
                ]
            ],
        )
        lines.append("")
        _append_markdown_table(
            lines,
            headers=["Turns", "Flagged Turns", "Audible Slow Turns", "Primary Turn"],
            rows=[
                [
                    str(session_scorecard.get("turn_count") or 0),
                    str(session_scorecard.get("flagged_turn_count") or 0),
                    str(session_scorecard.get("audible_slow_turn_count") or 0),
                    str(session_scorecard.get("primary_turn_number") or "N/A"),
                ]
            ],
        )

        lines.append("")
        lines.append("### Turn Summary Matrix")
        if turn_summary_matrix:
            _append_markdown_table(
                lines,
                headers=[
                    "Turn",
                    "Type",
                    "Transcript",
                    "AI Response",
                    "Total",
                    "User->Filler Audible",
                    "User->Agent Audible",
                    "Audible Filler",
                    "Filler End->Agent Audible",
                    "STT Lag",
                    "Runtime->Filler",
                    "Tool",
                    "LLM",
                    "Bottleneck",
                    "Owner",
                    "Markers",
                ],
                rows=[
                    [
                        str(row.get("turn_number") or "N/A"),
                        f"`{row.get('turn_type') or 'unknown'}`",
                        row.get("transcript") or "N/A",
                        row.get("ai_response") or "N/A",
                        _fmt_ms(row.get("total_ms")),
                        _fmt_ms(row.get("user_speak_end_to_filler_audible_ms")),
                        _fmt_ms(row.get("user_speak_end_to_agent_audible_ms")),
                        _fmt_ms(row.get("audible_filler_ms")),
                        _fmt_ms(row.get("filler_audio_end_to_agent_audible_ms")),
                        _fmt_ms(row.get("stt_lag_ms")),
                        _fmt_ms(row.get("runtime_to_filler_ms")),
                        _fmt_ms(row.get("tool_ms")),
                        _fmt_ms(row.get("llm_ms")),
                        f"`{row.get('bottleneck') or 'none'}`",
                        f"`{row.get('owner') or 'unknown'}`",
                        "<br>".join(row.get("markers") or []) or "—",
                    ]
                    for row in turn_summary_matrix
                ],
            )
        else:
            lines.append("- No turn summary rows extracted")

        lines.append("")
        lines.append("### Expanded Timelines")
        if expanded_timelines:
            for timeline in expanded_timelines:
                lines.append("")
                lines.append(
                    f"#### Turn {timeline.get('turn_number')} "
                    f"(`{timeline.get('selection_reason') or 'selected'}`)"
                )
                lines.append(f"- Transcript: `{timeline.get('transcript') or 'N/A'}`")
                lines.append(f"- AI: {timeline.get('ai_response') or 'N/A'}")
                lines.append("```text")
                lines.extend(timeline.get("lines") or ["no timeline extracted"])
                lines.append("```")
        else:
            lines.append("- No expanded timelines extracted")

        lines.append("")
        lines.append("### Layer Diagnostics")
        if layer_diagnostics:
            _append_markdown_table(
                lines,
                headers=["Layer", "Coverage", "Evidence", "Key Metric", "Status"],
                rows=[
                    [
                        f"`{layer.get('layer') or 'unknown'}`",
                        f"`{layer.get('coverage') or 'unknown'}`",
                        f"`{layer.get('evidence_level') or 'unknown'}`",
                        (
                            next(
                                (
                                    f"{key}={_fmt_ms(value) if key.endswith('_ms') else value}"
                                    for key, value in (layer.get("key_metrics") or {}).items()
                                    if value not in (None, "", [], {})
                                ),
                                "N/A",
                            )
                        ),
                        "[SUSPECT]" if layer.get("issue_signals") else "OK",
                    ]
                    for layer in layer_diagnostics
                ],
            )
        else:
            lines.append("- No per-layer diagnostics extracted")

        lines.append("")
        lines.append("### Evidence / Blind Spots")
        if evidence_registry:
            _append_markdown_table(
                lines,
                headers=["Signal", "Value", "Evidence", "Owner", "Source"],
                rows=[
                    [
                        entry.get("signal") or "unknown",
                        entry.get("value") or "N/A",
                        f"`{entry.get('evidence_level') or 'unknown'}`",
                        f"`{entry.get('owner') or 'unknown'}`",
                        entry.get("source_ref") or "N/A",
                    ]
                    for entry in evidence_registry
                ],
            )
        else:
            lines.append("- No evidence registry extracted")

        lines.append("")
        lines.append("### Basic Judgment")
        lines.append(f"- Diagnostic status: `{basic_judgment.get('diagnostic_status') or 'unknown'}`")
        lines.append(f"- Outcome category: `{basic_judgment.get('outcome_category') or 'unknown'}`")
        lines.append(f"- Severity: `{basic_judgment.get('severity') or 'unknown'}`")
        lines.append(f"- Owner: `{basic_judgment.get('owner') or 'unknown'}`")
        lines.append(f"- Confidence: `{basic_judgment.get('confidence') or 'unknown'}`")
        lines.append(f"- Customer impact: {basic_judgment.get('customer_impact') or 'N/A'}")
        lines.append(f"- Actionable now: `{'yes' if basic_judgment.get('actionable_now') else 'no'}`")
        lines.append(f"- Reported symptom: `{basic_judgment.get('reported_symptom') or 'not_provided'}`")
        lines.append(f"- Assessment: `{basic_judgment.get('symptom_assessment') or 'not_evaluated'}`")

        lines.append("")
        lines.append("### AI Diagnosis Report")
        lines.append(f"- Summary: {ai_diagnosis_report.get('summary') or 'No AI diagnosis summary generated.'}")
        if ai_diagnosis_report.get("evidence"):
            for item in ai_diagnosis_report.get("evidence", []):
                lines.append(f"- Evidence: {item}")
        else:
            lines.append("- Evidence: no evidence synthesized")
        if ai_diagnosis_report.get("gaps"):
            for item in ai_diagnosis_report.get("gaps", []):
                lines.append(f"- Gap: {item}")
        else:
            lines.append("- Gap: none recorded")

        component_coverage = session.get("component_coverage") or {}
        lines.append("")
        lines.append("### Component Coverage")
        lines.append(f"- Trace completeness: `{component_coverage.get('trace_completeness') or 'unknown'}`")
        counts = component_coverage.get("counts", {})
        if counts:
            for component, count in counts.items():
                lines.append(f"- `{component}`: {count} log(s)")
        lines.append(
            f"- Missing components: "
            f"{', '.join(f'`{item}`' for item in component_coverage.get('missing_components', [])) or 'None'}"
        )

        start_conversation = session.get("start_conversation") or {}
        lines.append("")
        lines.append("### Nova / Start Conversation")
        lines.append(f"- Nova path: {'yes' if start_conversation.get('is_nova') else 'no'}")
        lines.append(f"- Request ID: `{start_conversation.get('request_id') or 'N/A'}`")
        lines.append(f"- Status: `{start_conversation.get('status') or 'unknown'}`")
        lines.append(
            f"- Timing: start=`{start_conversation.get('started_at') or 'N/A'}` "
            f"end=`{start_conversation.get('completed_at') or 'N/A'}` "
            f"duration={_fmt_ms(start_conversation.get('duration_ms'))}"
        )
        lines.append(f"- Account ID: `{start_conversation.get('account_id') or 'N/A'}`")
        lines.append(f"- Conversation ID: `{start_conversation.get('conversation_id') or 'N/A'}`")
        lines.append(f"- Assistant ID: `{start_conversation.get('assistant_id') or 'N/A'}`")
        lines.append(f"- gRPC address: `{start_conversation.get('grpc_address') or 'N/A'}`")

        session_outcome = session.get("session_outcome") or {}
        lines.append("")
        lines.append("### Session Outcome")
        lines.append(f"- End reason: `{session_outcome.get('end_reason') or 'N/A'}`")
        lines.append(f"- End timestamp: `{session_outcome.get('end_timestamp') or 'N/A'}`")
        lines.append(f"- Close event: `{session_outcome.get('close_event') or 'N/A'}`")

        assistant_configuration = session.get("assistant_configuration") or {}
        lines.append("")
        lines.append("### Assistant Configuration")
        lines.append(f"- Source: `{assistant_configuration.get('source') or 'N/A'}`")
        lines.append(f"- Assistant ID: `{assistant_configuration.get('assistant_id') or 'N/A'}`")
        lines.append(
            f"- External assistant ID: `{assistant_configuration.get('external_assistant_id') or 'N/A'}`"
        )
        lines.append(
            f"- Config provider: `{assistant_configuration.get('configuration_provider_url') or 'N/A'}`"
        )
        lines.append(f"- Application ID: `{assistant_configuration.get('application_id') or 'N/A'}`")
        lines.append(
            f"- Solution / groupTag: `{assistant_configuration.get('solution') or 'N/A'}` / "
            f"`{assistant_configuration.get('group_tag') or 'N/A'}`"
        )
        lines.append(f"- Voice ID: `{assistant_configuration.get('voice_id') or 'N/A'}`")
        lines.append(
            f"- Languages: {', '.join(f'`{item}`' for item in assistant_configuration.get('languages', [])) or 'None'}"
        )
        lines.append(f"- Website: `{assistant_configuration.get('website') or 'N/A'}`")
        lines.append(
            f"- Tools ({assistant_configuration.get('tool_count', 0)}): "
            f"{', '.join(f'`{item}`' for item in assistant_configuration.get('tool_names', [])) or 'None'}"
        )
        lines.append(
            f"- Enabled skills: "
            f"{', '.join(f'`{item}`' for item in assistant_configuration.get('raw_enabled_skills', [])) or 'None'}"
        )
        lines.append(
            f"- Graph bundle: `{assistant_configuration.get('graph_bundle') or 'N/A'}`"
        )
        lines.append(
            f"- Graph skills: "
            f"{', '.join(f'`{item}`' for item in assistant_configuration.get('graph_skills', [])) or 'None'}"
        )
        feature_flags = assistant_configuration.get("feature_flags") or {}
        if feature_flags:
            lines.append("- Feature flags:")
            for key, value in feature_flags.items():
                rendered_value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
                lines.append(f"- `{key}` = `{rendered_value}`")
        else:
            lines.append("- Feature flags: none extracted")
        nca_flag_evaluations = assistant_configuration.get("nca_flag_evaluations") or {}
        if nca_flag_evaluations:
            lines.append("- NCA flag evaluations:")
            for key, value in nca_flag_evaluations.items():
                lines.append(f"- `{key}` = `{value}`")
        else:
            lines.append("- NCA flag evaluations: none extracted")

        correlation_ids = session.get("correlation_ids") or {}
        lines.append("")
        lines.append("### Correlation IDs")
        correlation_order = (
            "session_id",
            "conversation_id",
            "account_id",
            "assistant_id",
            "external_assistant_id",
            "start_conversation_request_id",
            "srs_session_id",
            "sgs_session_id",
            "speech_recognition_request_id",
            "speech_generation_request_id",
            "init_completion_id",
            "greeting_completion_id",
        )
        for key in correlation_order:
            lines.append(f"- `{key}`: `{correlation_ids.get(key) or 'N/A'}`")

        latency_path = session.get("latency_path") or "unknown"
        latency_buckets = session.get("latency_buckets") or _build_latency_buckets(session.get("latency_segments") or [])
        latency_segments = session.get("latency_segments") or []
        lines.append("")
        lines.append("### Latency Executive View")
        lines.append(f"- Path: `{latency_path}`")
        for bucket_name in LATENCY_BUCKET_ORDER:
            bucket = latency_buckets.get(bucket_name) or {}
            lines.append(
                f"- `{bucket_name}`: duration={_fmt_ms(bucket.get('duration_ms'))} "
                f"segments={bucket.get('segment_count', 0)}"
            )

        lines.append("")
        lines.append("### Latency Segments")
        if latency_segments:
            for segment in latency_segments:
                turn_suffix = f" turn={segment['turn_number']}" if segment.get("turn_number") is not None else ""
                lines.append(
                    f"- `{segment['segment_name']}` bucket=`{segment['bucket']}` "
                    f"duration={_fmt_ms(segment.get('duration_ms'))} "
                    f"evidence=`{segment.get('evidence_level') or 'unknown'}` "
                    f"owner=`{segment.get('owner') or 'unknown'}`{turn_suffix}"
                )
        else:
            lines.append("- No latency segments extracted")

        manual_rca_view = session.get("manual_rca_view") or {}
        filler_turns = manual_rca_view.get("filler_turns") or []
        lines.append("")
        lines.append("### Manual RCA View")
        if filler_turns:
            for filler_turn in filler_turns:
                lines.append(
                    f"- Turn `{filler_turn.get('turn_number')}` transcript="
                    f"`{_shorten(str(filler_turn.get('user_transcript') or ''))}`"
                )
                timestamps = filler_turn.get("timestamps") or {}
                segments_ms = filler_turn.get("segments_ms") or {}
                lines.append(
                    f"- matched interim -> final: {_fmt_ms(segments_ms.get('srs_matched_interim_to_final_ms'))} "
                    f"(`{timestamps.get('matched_interim_timestamp') or 'N/A'}` -> "
                    f"`{timestamps.get('matched_final_timestamp') or 'N/A'}`)"
                )
                lines.append(
                    f"- pending window: {_fmt_ms(segments_ms.get('assistant_runtime_pending_window_ms'))} "
                    f"(`{timestamps.get('pending_set_timestamp') or 'N/A'}` -> "
                    f"`{timestamps.get('pending_finalize_timestamp') or 'N/A'}`)"
                )
                lines.append(
                    f"- request -> filler TTS send: "
                    f"{_fmt_ms(segments_ms.get('assistant_runtime_request_to_filler_tts_send_ms'))} "
                    f"(`{timestamps.get('request_timestamp') or 'N/A'}` -> "
                    f"`{timestamps.get('filler_tts_request_timestamp') or 'N/A'}`)"
                )
                lines.append(
                    f"- request -> filler ready: {_fmt_ms(segments_ms.get('nca_request_to_filler_ready_ms'))} "
                    f"(`{timestamps.get('request_timestamp') or 'N/A'}` -> "
                    f"`{timestamps.get('nca_filler_ready_timestamp') or 'N/A'}`)"
                )
                lines.append(
                    f"- filler ready -> ResponseStart: "
                    f"{_fmt_ms(segments_ms.get('nca_filler_ready_to_response_start_ms'))} "
                    f"(`{timestamps.get('nca_filler_ready_timestamp') or 'N/A'}` -> "
                    f"`{timestamps.get('nca_filler_response_start_timestamp') or 'N/A'}`)"
                )
                lines.append(
                    f"- filler race: {_fmt_ms(segments_ms.get('nca_filler_race_ms'))}"
                )
                lines.append(
                    f"- TTS send -> first chunk: {_fmt_ms(segments_ms.get('tts_send_to_first_chunk_ms'))} "
                    f"(`{timestamps.get('filler_tts_request_timestamp') or 'N/A'}` -> "
                    f"`{timestamps.get('filler_first_chunk_timestamp') or 'N/A'}`)"
                )
                lines.append(
                    f"- filler audio end -> agent audible: "
                    f"{_fmt_ms((segments_ms.get('filler_audio_end_to_agent_audible_ms') if segments_ms.get('filler_audio_end_to_agent_audible_ms') is not None else segments_ms.get('filler_playback_terminal_to_agent_playback_start_ms')))} "
                    f"(`{timestamps.get('filler_playback_terminal_timestamp') or 'N/A'}` "
                    f"{timestamps.get('filler_playback_terminal_state') or 'unknown'} -> "
                    f"`{timestamps.get('agent_playback_start_proxy_timestamp') or 'N/A'}`)"
                )
                lines.append(
                    f"- audible filler from request: "
                    f"{_fmt_ms(segments_ms.get('audible_filler_from_request_ms'))}"
                )
                lines.append(
                    f"- audible filler from matched interim: "
                    f"{_fmt_ms(segments_ms.get('audible_filler_from_matched_interim_ms'))}"
                )
                lines.append(
                    f"- user speak end -> filler audible: "
                    f"{_fmt_ms(segments_ms.get('user_speak_end_to_filler_audible_ms'))}"
                )
                lines.append(
                    f"- user speak end -> agent audible: "
                    f"{_fmt_ms(segments_ms.get('user_speak_end_to_agent_audible_ms'))}"
                )
        else:
            lines.append("- No manual RCA filler breakdown extracted")

        lines.append("")
        lines.append("### Layer Diagnostics Details")
        if layer_diagnostics:
            for layer in layer_diagnostics:
                layer_name = layer.get("layer") or "unknown"
                lines.append(
                    f"- `{layer_name}` coverage=`{layer.get('coverage') or 'unknown'}` "
                    f"evidence=`{layer.get('evidence_level') or 'unknown'}` "
                    f"components={layer.get('component_count', 0)}"
                )
                key_metrics = layer.get("key_metrics") or {}
                if key_metrics:
                    metric_parts = []
                    for key, value in key_metrics.items():
                        if value in (None, "", [], {}):
                            continue
                        if isinstance(value, bool):
                            metric_parts.append(f"{key}={str(value).lower()}")
                        elif isinstance(value, (int, float)) and key.endswith("_ms"):
                            metric_parts.append(f"{key}={_fmt_ms(value)}")
                        else:
                            metric_parts.append(f"{key}={value}")
                    if metric_parts:
                        lines.append(f"- metrics: {'; '.join(metric_parts)}")
                issue_signals = [signal for signal in (layer.get("issue_signals") or []) if signal]
                if issue_signals:
                    lines.append(f"- issue signals: {'; '.join(issue_signals)}")
                blind_spots = [spot for spot in (layer.get("blind_spots") or []) if spot]
                if blind_spots:
                    lines.append(f"- blind spots: {'; '.join(blind_spots)}")
        else:
            lines.append("- No per-layer diagnostics extracted")

        key_timeline = session.get("key_timeline") or []
        lines.append("")
        lines.append("### Key Timeline")
        if key_timeline:
            for entry in key_timeline[:12]:
                lines.append(
                    f"- `{entry.get('timestamp') or 'N/A'}` `{entry.get('event') or 'unknown'}`: {entry.get('detail') or ''}"
                )
        else:
            lines.append("- No timeline events extracted")

        lines.append("")
        lines.append("### Speech Linkage")
        lines.append("")
        lines.append("| Component | Expected ID | Linked | First Seen | Last Seen | Disconnect Signals |")
        lines.append("|-----------|-------------|--------|------------|-----------|--------------------|")
        for component_key in ("srs", "sgs"):
            component = session["speech"][component_key]
            lines.append(
                f"| {component_key.upper()} | `{component['expected_session_id'] or 'N/A'}` | "
                f"{'yes' if component['linked'] else 'no'} | "
                f"`{component['first_seen'] or 'N/A'}` | `{component['last_seen'] or 'N/A'}` | "
                f"{len(component['disconnect_events'])} |"
            )

        srs = session["speech"]["srs"]
        lines.append("")
        lines.append("### SRS")
        lines.append(f"- Observed IDs: {', '.join(f'`{item}`' for item in srs['observed_session_ids']) or 'None'}")
        lines.append(
            f"- ASR latency: avg={_fmt_ms(srs['latency']['asr_latency_ms']['avg_ms'])}, "
            f"max={_fmt_ms(srs['latency']['asr_latency_ms']['max_ms'])}, "
            f"samples={srs['latency']['asr_latency_ms']['count']}"
        )
        lines.append(
            f"- IVA delivery latency: avg={_fmt_ms(srs['latency']['iva_delivery_latency_ms']['avg_ms'])}, "
            f"max={_fmt_ms(srs['latency']['iva_delivery_latency_ms']['max_ms'])}, "
            f"samples={srs['latency']['iva_delivery_latency_ms']['count']}"
        )
        if srs["disconnect_events"]:
            lines.append("- Disconnect / teardown:")
            for event in srs["disconnect_events"][-5:]:
                lines.append(
                    f"- `{event['timestamp'] or 'N/A'}` id=`{event['session_id'] or 'N/A'}` "
                    f"error={'yes' if event['is_error'] else 'no'} type=`{event['type']}`: {event['message']}"
                )
        else:
            lines.append("- Disconnect / teardown: none detected")

        sgs = session["speech"]["sgs"]
        lines.append("")
        lines.append("### SGS")
        lines.append(f"- Observed IDs: {', '.join(f'`{item}`' for item in sgs['observed_session_ids']) or 'None'}")
        lines.append(f"- Generate requests: {sgs['request_count']}")
        lines.append(f"- Cancel requests: {sgs['cancel_count']}")
        lines.append(
            f"- First chunk latency: avg={_fmt_ms(sgs['latency']['ttfc_ms']['avg_ms'])}, "
            f"max={_fmt_ms(sgs['latency']['ttfc_ms']['max_ms'])}, "
            f"samples={sgs['latency']['ttfc_ms']['count']}"
        )
        lines.append(
            f"- Playback duration: avg={_fmt_ms(sgs['latency']['playback_duration_ms']['avg_ms'])}, "
            f"max={_fmt_ms(sgs['latency']['playback_duration_ms']['max_ms'])}, "
            f"samples={sgs['latency']['playback_duration_ms']['count']}"
        )
        lines.append(f"- Last audio end: `{sgs['last_audio_end'] or 'N/A'}`")
        if sgs["disconnect_events"]:
            lines.append("- Disconnect / interruption:")
            for event in sgs["disconnect_events"][-5:]:
                request_id = f" request_id=`{event['request_id']}`" if event.get("request_id") else ""
                sseq = f" sseq={event['sseq']}" if event.get("sseq") is not None else ""
                lines.append(
                    f"- `{event['timestamp'] or 'N/A'}` id=`{event['session_id'] or 'N/A'}`{request_id}{sseq} "
                    f"error={'yes' if event['is_error'] else 'no'} type=`{event['type']}`: {event['message']}"
                )
        else:
            lines.append("- Disconnect / interruption: none detected")

        lines.append("")
        lines.append("### Turn Diagnostics")
        for turn in session["turns"]:
            lines.append("")
            lines.append(f"#### Turn {turn['turn_number']} ({turn['turn_type']})")
            lines.append(
                f"- Latency: duration={_fmt_ms(turn.get('duration_ms'))}, "
                f"ttft={_fmt_ms(turn.get('ttft_ms'))}, "
                f"llm_total={_fmt_ms((turn.get('latency_breakdown') or {}).get('llm_total_ms'))}, "
                f"non_llm={_fmt_non_negative_ms((turn.get('latency_breakdown') or {}).get('non_llm_ms'))}"
            )
            if turn.get("user_transcript"):
                lines.append(f"- User: {turn['user_transcript']}")
            if turn.get("ai_response"):
                lines.append(f"- AI: {turn['ai_response']}")
            if turn.get("tool_calls"):
                lines.append("- Tool calls:")
                for call in turn["tool_calls"]:
                    lines.append(
                        f"- `{call['tool_type']}` `{call['tool_name']}` status={call['status']} "
                        f"duration={_fmt_ms(call.get('duration_ms'))} "
                        f"components={','.join(call.get('observed_components', [])) or 'unknown'} "
                        f"source={call.get('tool_type_source', 'unknown')} "
                        f"confidence={call.get('tool_type_confidence', 'low')}"
                    )
            else:
                lines.append("- Tool calls: none")
            if turn.get("contradictions"):
                lines.append("- Contradictions:")
                for contradiction in turn["contradictions"]:
                    lines.append(
                        f"- [{contradiction['severity']}] {contradiction['type']}: {contradiction['message']}"
                    )
            if turn.get("anomalies"):
                lines.append("- Anomalies:")
                for anomaly in turn["anomalies"]:
                    lines.append(
                        f"- [{anomaly.get('severity', 'info')}] {anomaly.get('type', 'unknown')}: "
                        f"{anomaly.get('message', '')}"
                    )

        lines.append("")
        lines.append("### Recommended Next Actions")
        for action in ai_diagnosis_report.get("next_actions", []):
            lines.append(f"- {action}")

    rendered = "\n".join(lines).rstrip() + "\n"
    if lang == "en":
        return rendered
    if lang == "zh":
        return _translate_markdown_to_zh(rendered)
    raise ValueError(f"Unsupported language: {lang}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a generic IVA diagnostic report from saved trace directories.")
    parser.add_argument("session_dirs", nargs="+", help="Saved iva session output directories")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--lang", choices=["zh", "en"], default="zh", help="Markdown output language")
    parser.add_argument("--output", "-o", help="Write the report to a file")
    parser.add_argument("--reported-symptom", help="Optional user-reported symptom to map against trace evidence")
    args = parser.parse_args()

    sessions = [
        _build_session_diagnostic(Path(session_dir), reported_symptom=args.reported_symptom)
        for session_dir in args.session_dirs
    ]
    payload = {
        "session_count": len(sessions),
        "tool_call_count": sum(session["tool_call_count"] for session in sessions),
        "aggregate": _aggregate(sessions),
        "sessions": sessions,
    }

    output = (
        json.dumps(payload, indent=2, ensure_ascii=False)
        if args.format == "json"
        else render_markdown(payload, lang=args.lang)
    )

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
