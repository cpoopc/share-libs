import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "agents"
    / "skills"
    / "iva-logtracer"
    / "scripts"
    / "diagnostic_report.py"
)

SPEC = importlib.util.spec_from_file_location("diagnostic_report", SCRIPT_PATH)
diagnostic_report = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(diagnostic_report)


def test_parse_srs_log_extracts_linkage_disconnects_and_latency(tmp_path: Path) -> None:
    log_path = tmp_path / "cprc_srs_message.log"
    log_path.write_text(
        "\n".join(
            [
                '[2026-03-23T17:43:19.862Z] INFO Request method=POST uri=/v1/session/0d326d22-f9c3-4ec1-a68b-0b9b4117f89c',
                '[2026-03-23T17:43:20.200Z] INFO recognize{session_id="0d326d22-f9c3-4ec1-a68b-0b9b4117f89c"}: recognize stream established',
                '[2026-03-23T17:43:24.673Z] INFO transcription{session_id=0d326d22-f9c3-4ec1-a68b-0b9b4117f89c}: Process transcript result is_final=false words=6',
                '[2026-03-23T17:43:25.674Z] INFO transcription{session_id=0d326d22-f9c3-4ec1-a68b-0b9b4117f89c}: Process transcript result is_final=true words=6',
                '[2026-03-23T17:43:25.674Z] INFO transcription{session_id=0d326d22-f9c3-4ec1-a68b-0b9b4117f89c}: asr_latency=0.77',
                '[2026-03-23T17:43:29.823Z] INFO recognize{session_id="0d326d22-f9c3-4ec1-a68b-0b9b4117f89c"}: iva_delivery_latency=0.001',
                '[2026-03-23T17:46:03.999Z] WARN transcription{session_id=0d326d22-f9c3-4ec1-a68b-0b9b4117f89c}: Failed to send error message to transcript_tx: channel closed',
                '[2026-03-23T17:46:04.005Z] INFO recognize{session_id="0d326d22-f9c3-4ec1-a68b-0b9b4117f89c"}: Client disconnected, stopping IVA recognition',
            ]
        ),
        encoding="utf-8",
    )

    parsed = diagnostic_report._parse_srs_log(log_path, "0d326d22-f9c3-4ec1-a68b-0b9b4117f89c")

    assert parsed["linked"] is True
    assert parsed["latency"]["asr_latency_ms"]["avg_ms"] == 770.0
    assert parsed["latency"]["iva_delivery_latency_ms"]["avg_ms"] == 1.0
    assert parsed["finalization_pairs"][0]["duration_ms"] == pytest.approx(1001.0)
    assert len(parsed["disconnect_events"]) == 2
    assert parsed["disconnect_events"][0]["is_error"] is True


def test_parse_sgs_log_extracts_requests_interruptions_and_latency(tmp_path: Path) -> None:
    log_path = tmp_path / "cprc_sgs_message.log"
    log_path.write_text(
        "\n".join(
            [
                '[2026-03-23T17:43:20.210Z] INFO synthesis_session{session_id=118cdde9-60a8-4236-9eb1-abd719f193e9}: new generate request request_session_id=118cdde9-60a8-4236-9eb1-abd719f193e9 req=Some(Request(GenerateRequestData { sseq: 1, text: "hello" }))',
                '[2026-03-23T17:43:20.381Z] INFO handle_synthesis_request{session_id=118cdde9-60a8-4236-9eb1-abd719f193e9 request_id=118cdde9-60a8-4236-9eb1-abd719f193e9-1}: first chunk received latency=0.170605043',
                '[2026-03-23T17:43:26.850Z] INFO synthesis_session{session_id=118cdde9-60a8-4236-9eb1-abd719f193e9}: Received event: playback finished audio_duration=AudioDuration { playback_id: 0, duration_ms: 6460 } request_key=SynthesisRequestKey { session_id: "118cdde9-60a8-4236-9eb1-abd719f193e9", sseq: 1 }',
                '[2026-03-23T17:44:27.428Z] INFO synthesis_session{session_id=118cdde9-60a8-4236-9eb1-abd719f193e9}: new generate request request_session_id=118cdde9-60a8-4236-9eb1-abd719f193e9 req=Some(Cancel(CancelRequest { sseq: 12 }))',
                '[2026-03-23T17:44:27.430Z] INFO synthesis_session{session_id=118cdde9-60a8-4236-9eb1-abd719f193e9}: Received event: playback interrupted audio_duration=AudioDuration { playback_id: 8, duration_ms: 1700 } request_key=SynthesisRequestKey { session_id: "118cdde9-60a8-4236-9eb1-abd719f193e9", sseq: 12 }',
            ]
        ),
        encoding="utf-8",
    )

    parsed = diagnostic_report._parse_sgs_log(log_path, "118cdde9-60a8-4236-9eb1-abd719f193e9")

    assert parsed["linked"] is True
    assert parsed["request_count"] == 1
    assert parsed["cancel_count"] == 1
    assert parsed["generate_events"][0]["sseq"] == 1
    assert parsed["first_chunk_events"][0]["sseq"] == 1
    assert parsed["playback_events"][0]["state"] == "finished"
    assert parsed["playback_events"][1]["state"] == "interrupted"
    assert parsed["latency"]["ttfc_ms"]["avg_ms"] == pytest.approx(170.605043)
    assert parsed["latency"]["playback_duration_ms"]["max_ms"] == 6460.0
    assert len(parsed["disconnect_events"]) == 2


def test_build_manual_rca_view_extracts_filler_breakdown() -> None:
    speech = {
        "srs": {
            "finalization_pairs": [
                {
                    "interim_timestamp": "2026-03-30T23:48:20.560433Z",
                    "final_timestamp": "2026-03-30T23:48:21.561336Z",
                    "words": 6,
                    "duration_ms": 1000.903,
                }
            ],
            "latency": {},
        },
        "sgs": {
            "first_chunk_events": [
                {
                    "timestamp": "2026-03-30T23:48:25.216374Z",
                    "request_id": "5011f1bc-021a-4862-aea1-1421825aa3db-15",
                    "sseq": 15,
                    "latency_ms": 403.490365,
                },
                {
                    "timestamp": "2026-03-30T23:48:25.930000Z",
                    "request_id": "5011f1bc-021a-4862-aea1-1421825aa3db-16",
                    "sseq": 16,
                    "latency_ms": 110.0,
                }
            ],
            "playback_events": [
                {
                    "timestamp": "2026-03-30T23:48:25.980000Z",
                    "request_id": "5011f1bc-021a-4862-aea1-1421825aa3db-15",
                    "sseq": 15,
                    "state": "finished",
                    "duration_ms": 760.0,
                }
            ],
            "latency": {},
        },
    }
    assistant_runtime_latency = {
        "request_events": [{"timestamp": "2026-03-30T23:48:23.881000Z", "completion_id": "c-1"}],
        "generation_requests": [
            {"timestamp": "2026-03-30T23:48:24.808000Z", "sseq": 15, "is_final": False},
            {"timestamp": "2026-03-30T23:48:25.900000Z", "sseq": 16, "is_final": False},
        ],
        "filler_ttft_events": [{"timestamp": "2026-03-30T23:48:24.808000Z", "ttft_ms": 926.0}],
        "pending_windows": [
            {
                "timestamp": "2026-03-30T23:48:21.565000Z",
                "set_timestamp": "2026-03-30T23:48:21.565000Z",
                "finalize_timestamp": "2026-03-30T23:48:23.881000Z",
                "pending_merge_window_ms": 2316.0,
            }
        ],
    }
    nca_latency = {
        "filler_race_events": [{"timestamp": "2026-03-30T23:48:24.290000Z", "duration_ms": 406.0}],
        "filler_generation_events": [{"timestamp": "2026-03-30T23:48:24.381000Z"}],
        "response_start_events": [{"timestamp": "2026-03-30T23:48:24.803000Z", "component": "filler"}],
    }
    turns = [
        {
            "turn_number": 7,
            "turn_type": "user_turn",
            "start_timestamp": "2026-03-30T23:48:23.881000Z",
            "end_timestamp": "2026-03-30T23:48:46.866000Z",
            "user_transcript": "version of my RingCentral phone.",
        }
    ]

    view = diagnostic_report._build_manual_rca_view(
        speech=speech,
        assistant_runtime_latency=assistant_runtime_latency,
        nca_latency=nca_latency,
        turns=turns,
    )

    filler_turn = view["filler_turns"][0]
    assert filler_turn["turn_number"] == 7
    assert filler_turn["segments_ms"]["srs_matched_interim_to_final_ms"] == pytest.approx(1000.903)
    assert filler_turn["segments_ms"]["assistant_runtime_pending_window_ms"] == pytest.approx(2316.0)
    assert filler_turn["segments_ms"]["assistant_runtime_request_to_filler_tts_send_ms"] == pytest.approx(927.0)
    assert filler_turn["segments_ms"]["nca_request_to_filler_ready_ms"] == pytest.approx(500.0)
    assert filler_turn["segments_ms"]["nca_filler_ready_to_response_start_ms"] == pytest.approx(422.0)
    assert filler_turn["segments_ms"]["tts_send_to_first_chunk_ms"] == pytest.approx(408.374)
    assert filler_turn["segments_ms"]["audible_filler_from_request_ms"] == pytest.approx(1335.374)
    assert filler_turn["segments_ms"]["audible_filler_from_matched_interim_ms"] == pytest.approx(4655.941)
    assert filler_turn["segments_ms"]["user_speak_end_to_filler_audible_ms"] == pytest.approx(4655.941)
    assert filler_turn["timestamps"]["filler_playback_terminal_timestamp"] == "2026-03-30T23:48:25.980000Z"
    assert filler_turn["timestamps"]["agent_first_chunk_timestamp"] == "2026-03-30T23:48:25.930000Z"
    assert filler_turn["timestamps"]["agent_playback_start_proxy_timestamp"] == "2026-03-30T23:48:25.980000Z"
    assert filler_turn["segments_ms"]["filler_playback_terminal_to_agent_playback_start_ms"] == pytest.approx(0.0)
    assert filler_turn["segments_ms"]["user_speak_end_to_agent_audible_ms"] == pytest.approx(5419.567)


def test_user_turn_variants_count_as_user_turns_for_snapshot_and_scorecard() -> None:
    turns = [
        {"turn_number": 1, "turn_type": "greeting", "tool_calls": [], "contradictions": [], "anomalies": []},
        {
            "turn_number": 2,
            "turn_type": "user_turn_interrupted",
            "duration_ms": 14124.0,
            "tool_calls": [],
            "contradictions": [],
            "anomalies": [{"type": "nca_warning", "severity": "warning", "message": "gap"}],
        },
        {
            "turn_number": 3,
            "turn_type": "user_turn_continued",
            "duration_ms": 7228.0,
            "tool_calls": [],
            "contradictions": [],
            "anomalies": [],
        },
    ]

    snapshot = diagnostic_report._build_diagnostic_snapshot(
        total_turns=3,
        turns=turns,
        tool_call_count=0,
        component_coverage={"trace_completeness": "high", "missing_components": []},
        session_outcome={"end_reason": "CallForwarded"},
    )
    judgment = diagnostic_report._build_basic_judgment(
        reported_symptom=None,
        diagnostic_snapshot=snapshot,
        start_conversation={"status": "success"},
        component_coverage={"trace_completeness": "high"},
        speech={"srs": {"linked": True}, "sgs": {"linked": True}},
        turns=turns,
        session_outcome={"end_reason": "CallForwarded"},
    )
    scorecard = diagnostic_report._build_session_scorecard(
        session_id="s-variant",
        latency_path="nova",
        basic_judgment=judgment,
        component_coverage={
            "counts": {
                "assistant_runtime": 10,
                "agent_service": 1,
                "nca": 8,
                "cprc_srs": 4,
                "cprc_sgs": 4,
                "aig": 1,
                "gmg": 1,
            },
            "missing_components": [],
        },
        turn_summary_matrix=[
            {
                "turn_number": 1,
                "turn_type": "greeting",
                "total_ms": 15000.0,
                "bottleneck_duration_ms": None,
                "bottleneck": "none",
                "owner": "unknown",
                "flagged": True,
                "user_perceived_slow": False,
            },
            {
                "turn_number": 2,
                "turn_type": "user_turn_interrupted",
                "total_ms": 14000.0,
                "bottleneck_duration_ms": 5300.0,
                "bottleneck": "LLM total",
                "owner": "GMG/LLM",
                "flagged": True,
                "user_perceived_slow": True,
            },
            {
                "turn_number": 3,
                "turn_type": "user_turn_continued",
                "total_ms": 7000.0,
                "bottleneck_duration_ms": 4400.0,
                "bottleneck": "transfer_call",
                "owner": "Tooling",
                "flagged": True,
                "user_perceived_slow": False,
            },
        ],
    )

    assert snapshot["has_user_turns"] is True
    assert "User turns observed: yes" in snapshot["key_facts"]
    assert judgment["has_user_turns"] is True
    assert scorecard["primary_turn_number"] == 2
    assert scorecard["user_perceived_slow"] is True
    assert scorecard["attribution_confidence"] == "high"


def test_action_summary_surfaces_claim_and_downgrades_attribution_when_owner_coverage_is_missing() -> None:
    turn_summary_matrix = [
        {
            "turn_number": 2,
            "turn_type": "user_turn_interrupted",
            "transcript": "Need to change",
            "total_ms": 14124.0,
            "bottleneck_duration_ms": 5370.0,
            "bottleneck": "LLM total",
            "owner": "GMG/LLM",
            "flagged": True,
            "user_perceived_slow": True,
            "filler_audio_end_to_agent_audible_ms": 2246.0,
            "filler_to_agent_gap_ms": 2246.0,
            "user_speak_end_to_agent_audible_ms": 4081.0,
            "llm_ms": 5370.0,
            "tool_ms": None,
        }
    ]
    component_coverage = {
        "counts": {
            "assistant_runtime": 20,
            "agent_service": 0,
            "nca": 18,
            "cprc_srs": 8,
            "cprc_sgs": 8,
            "aig": 0,
            "gmg": 0,
        },
        "missing_components": ["agent_service", "aig", "gmg"],
    }
    scorecard = diagnostic_report._build_session_scorecard(
        session_id="s-gap",
        latency_path="nova",
        basic_judgment={"confidence": "high"},
        component_coverage=component_coverage,
        turn_summary_matrix=turn_summary_matrix,
    )
    action_summary = diagnostic_report._build_action_summary(
        session_scorecard=scorecard,
        turn_summary_matrix=turn_summary_matrix,
        component_coverage=component_coverage,
    )

    assert scorecard["likely_owner"] == "GMG/LLM"
    assert scorecard["attribution_confidence"] == "low"
    assert "`gmg`, `aig`" in scorecard["owner_note"]
    assert action_summary["customer_impact"] == "User likely heard a meaningful delay in turn 2."
    assert action_summary["strongest_claim"] == "Turn 2 had 2246 ms of silence after filler audio ended."
    assert action_summary["next_action"] == "Pull `gmg`, `aig` coverage for turn 2 before assigning owner."


def test_turn_summary_matrix_and_timeline_add_suspect_markers() -> None:
    turns = [
        {
            "turn_number": 2,
            "turn_type": "user_turn_interrupted",
            "duration_ms": 14124.0,
            "latency_breakdown": {"llm_total_ms": 5370.0, "non_llm_ms": 8754.0},
            "tool_calls": [],
            "contradictions": [],
            "anomalies": [{"type": "nca_warning", "severity": "warning", "message": "gap"}],
            "user_transcript": "Need to change",
        }
    ]
    manual_rca_view = {
        "filler_turns": [
            {
                "turn_number": 2,
                "user_transcript": "Need to change",
                "timestamps": {"agent_playback_start_proxy_timestamp": "2026-04-01T16:41:31.135Z"},
                "segments_ms": {
                    "srs_matched_interim_to_final_ms": 813.0,
                    "assistant_runtime_request_to_filler_tts_send_ms": 512.0,
                    "nca_request_to_filler_ready_ms": 459.0,
                    "nca_filler_ready_to_response_start_ms": 49.0,
                    "tts_send_to_first_chunk_ms": 169.0,
                    "audible_filler_from_request_ms": 681.0,
                    "user_speak_end_to_filler_audible_ms": 1494.0,
                    "filler_playback_terminal_to_agent_playback_start_ms": 2246.0,
                    "user_speak_end_to_agent_audible_ms": 3740.0,
                },
            }
        ]
    }

    rows = diagnostic_report._build_turn_summary_matrix(turns=turns, manual_rca_view=manual_rca_view)
    timelines = diagnostic_report._build_expanded_timelines(
        turns=turns,
        turn_summary_matrix=rows,
        manual_rca_view=manual_rca_view,
    )

    assert rows[0]["flagged"] is True
    assert "[SUSPECT] STT lag" in rows[0]["markers"]
    assert "[SUSPECT] filler audio end -> agent audible" in rows[0]["markers"]
    assert "[SUSPECT] LLM total" in rows[0]["markers"]
    assert "[SUSPECT] anomaly:nca_warning" in rows[0]["markers"]
    assert rows[0]["ai_response"] == "N/A"
    assert rows[0]["user_speak_end_to_filler_audible_ms"] == pytest.approx(1494.0)
    assert rows[0]["user_speak_end_to_agent_audible_ms"] == pytest.approx(3740.0)
    assert rows[0]["filler_audio_end_to_agent_audible_ms"] == pytest.approx(2246.0)
    assert any("[SUSPECT] filler audio end -> agent audible" in line for line in timelines[0]["lines"])


def test_parse_start_conversation_and_assistant_configuration_extracts_nova_and_skill_settings(tmp_path: Path) -> None:
    assistant_runtime_log = tmp_path / "assistant_runtime_message.log"
    nca_log = tmp_path / "nca_message.log"
    agent_service_log = tmp_path / "agent_service_message.log"
    summary_json = tmp_path / "summary.json"

    assistant_runtime_log.write_text(
        "\n".join(
            [
                '[2026-03-23T18:29:58.485Z] INFO Creating Nova conversation for accountId: 2252201020, requestId: ca99e01a-3640-445d-b0bb-b44209388044',
                '[2026-03-23T18:29:58.518Z] INFO POST https://intapi.ringcentral.com/ai/nova/v1/internal/start-conversation: OK, body: {"conversation":{"id":"ac469910-4598-44c0-a071-0f263785a964"},"assistant":{"id":"69618e02-79ad-4035-811f-c689ce7e70bc"},"systemMetadata":{"address":"dns:///aic-openai-service-grpc.production-ringcentral-application.svc.cluster.local:8280"}}',
                '[2026-03-23T18:29:58.519Z] INFO Nova conversation has been created: ac469910-4598-44c0-a071-0f263785a964, requestId: ca99e01a-3640-445d-b0bb-b44209388044',
                '[2026-03-23T18:29:58.520Z] INFO calculateFeatureFlags final feature flags: {"agent_type":"nova","nova_config":{"solution":"V1","model_group_tag":"gpt52","enableFiller":true},"hangup_tool_enabled":true}',
                '[2026-03-23T18:29:58.530Z] INFO Received init: {"info":{"languages":["en-US"],"website":"https://example.com","toolDefinitions":[{"name":"transfer_call"},{"name":"air_searchCompanyKnowledgeBase"}],"metadata":"{\\"featureFlags\\":{\\"solution\\":\\"V1\\",\\"groupTag\\":\\"gpt52\\"}}"}}',
                '[2026-03-23T18:29:58.540Z] INFO Speech recognition started: {"id":"sr-123"}',
                '[2026-03-23T18:29:58.541Z] INFO Speech generation started: {"id":"sg-123"}',
                '[2026-03-23T18:29:58.542Z] INFO Sending init request {"completionId":"init-123"}',
                '[2026-03-23T18:29:58.543Z] INFO Sending request {"completionId":"greet-123","payload":{"oneofKind":"generate"}}',
                '[2026-03-23T18:29:58.544Z] INFO Produced to Kafka, msg: {"metadata":{"agentType":"nova"},"context":{"accountId":2252201020,"assistantId":"69618e02-79ad-4035-811f-c689ce7e70bc","conversationId":"ac469910-4598-44c0-a071-0f263785a964"}}',
                '[2026-03-23T18:30:10.000Z] INFO Sending ConversationEndRequest for conversation ac469910-4598-44c0-a071-0f263785a964, reason: CallerDropped',
                '[2026-03-23T18:30:10.001Z] INFO [00:00:12.000] [state: listening] Conversation close by event: UserDisconnectEvent with reason: conversation closed',
            ]
        ),
        encoding="utf-8",
    )
    nca_log.write_text(
        "\n".join(
            [
                '[2026-03-23T18:29:58.600Z] INFO [AssistantConfig] Get external assistant config, ExternalAssistantLookupConfig(rcAccountId=2252201020, applicationId=IVA, externalAssistantId=69618e02-79ad-4035-811f-c689ce7e70bc, assistantConfigurationProviderUrl=https://intapi.ringcentral.com/ai/iva/v1/accounts/2252201020/assistants/69618e02-79ad-4035-811f-c689ce7e70bc/nova-assistant, rcExtensionId=2252201020, solution=V1, groupTag=gpt52)',
                '[2026-03-23T18:29:58.601Z] INFO [AssistantConfig] Assistant config found, id: 69618e02-79ad-4035-811f-c689ce7e70bc',
                '[2026-03-23T18:29:58.602Z] INFO [Tool] Retrieved tools: configs=2, schemas=2, tools=2',
                '[2026-03-23T18:29:58.603Z] INFO FFS flag evaluation: flagId=nova.nca.llm_request_timeout, value={"enabled":false,"timeout_ms":30000}, elapsed=1ms',
            ]
        ),
        encoding="utf-8",
    )
    agent_service_log.write_text(
        "\n".join(
            [
                '[2026-03-23T18:29:58.700Z] INFO Getting nova assistant configuration for extension undefined, assistantId 69618e02-79ad-4035-811f-c689ce7e70bc',
                '[2026-03-23T18:29:58.701Z] INFO Parsed feature flags: {"nova_config":{"solution":"V1","model_group_tag":"gpt52"},"hangup_tool_enabled":true}',
                '[2026-03-23T18:29:58.702Z] INFO Creating PBX Assistant Builder with solution=V1, modelGroupTag=gpt52',
                '[2026-03-23T18:29:58.703Z] INFO Assistant raw enabled skills: ["knowledgeBase","sms"]',
                '[2026-03-23T18:29:58.704Z] INFO Sampling the graph for bundle: multi-agent-gpt-4.1-v1, skills: KNOWLEDGE_BASE, SMS',
            ]
        ),
        encoding="utf-8",
    )
    summary_json.write_text(
        '{"session_id":"s-123","conversation_id":"ac469910-4598-44c0-a071-0f263785a964","srs_session_id":"srs-123","sgs_session_id":"sgs-123"}',
        encoding="utf-8",
    )

    start = diagnostic_report._parse_start_conversation(assistant_runtime_log)
    assistant_config = diagnostic_report._parse_assistant_configuration(tmp_path)
    ids = diagnostic_report._parse_correlation_ids(tmp_path, start, assistant_config)
    outcome = diagnostic_report._parse_session_outcome(tmp_path)
    coverage = diagnostic_report._build_component_coverage(
        {"summary": {"assistant_runtime": 10, "agent_service": 4, "nca": 8, "cprc_srs": 3, "cprc_sgs": 4, "aig": 0, "gmg": 0}}
    )
    snapshot = diagnostic_report._build_diagnostic_snapshot(
        total_turns=1,
        turns=[{"turn_type": "greeting", "tool_calls": [], "contradictions": [], "anomalies": []}],
        tool_call_count=0,
        component_coverage=coverage,
        session_outcome=outcome,
    )
    judgment = diagnostic_report._build_basic_judgment(
        reported_symptom="AIR answered wrong",
        diagnostic_snapshot=snapshot,
        start_conversation=start,
        component_coverage=coverage,
        speech={"srs": {"linked": True}, "sgs": {"linked": True}},
        turns=[{"turn_type": "greeting", "tool_calls": [], "contradictions": [], "anomalies": []}],
        session_outcome=outcome,
    )
    ai_report = diagnostic_report._build_ai_diagnosis_report(
        diagnostic_snapshot=snapshot,
        basic_judgment=judgment,
    )

    assert start["is_nova"] is True
    assert start["request_id"] == "ca99e01a-3640-445d-b0bb-b44209388044"
    assert start["status"] == "success"
    assert start["duration_ms"] == pytest.approx(34.0, abs=0.5)
    assert start["assistant_id"] == "69618e02-79ad-4035-811f-c689ce7e70bc"

    assert assistant_config["source"] == "agent_service"
    assert assistant_config["solution"] == "V1"
    assert assistant_config["group_tag"] == "gpt52"
    assert assistant_config["tool_count"] == 2
    assert assistant_config["tool_names"] == ["transfer_call", "air_searchCompanyKnowledgeBase"]
    assert assistant_config["raw_enabled_skills"] == ["knowledgeBase", "sms"]
    assert assistant_config["graph_bundle"] == "multi-agent-gpt-4.1-v1"
    assert assistant_config["graph_skills"] == ["KNOWLEDGE_BASE", "SMS"]
    assert assistant_config["nca_flag_evaluations"]["nova.nca.llm_request_timeout"] == '{"enabled":false,"timeout_ms":30000}'

    assert ids["account_id"] == 2252201020
    assert ids["assistant_id"] == "69618e02-79ad-4035-811f-c689ce7e70bc"
    assert ids["start_conversation_request_id"] == "ca99e01a-3640-445d-b0bb-b44209388044"
    assert ids["speech_recognition_request_id"] == "sr-123"
    assert ids["speech_generation_request_id"] == "sg-123"
    assert ids["init_completion_id"] == "init-123"
    assert ids["greeting_completion_id"] == "greet-123"
    assert outcome["end_reason"] == "CallerDropped"
    assert "Conversation close by event: UserDisconnectEvent" in outcome["close_event"]
    assert coverage["trace_completeness"] == "high"
    assert coverage["missing_components"] == ["aig", "gmg"]
    assert snapshot["diagnostic_status"] == "short_call"
    assert snapshot["session_shape"] == "greeting_only"
    assert snapshot["trace_completeness"] == "high"
    assert snapshot["confidence"] == "high"
    assert snapshot["top_signals"][0] == "Caller dropped during or immediately after greeting; the session never reached a user turn."
    assert judgment["outcome_category"] == "short_call"
    assert judgment["owner"] == "caller_or_call_flow"
    assert judgment["symptom_assessment"] == "not_confirmed"
    assert judgment["reported_symptom"] == "AIR answered wrong"
    assert ai_report["final_verdict"] == "Short call: the session ended with `CallerDropped` before AIR handled a user turn."
    assert ai_report["evidence"][0] == "Caller dropped during or immediately after greeting; the session never reached a user turn."
    assert ai_report["gaps"] == ["No major evidence gaps were detected in the available trace."]


@pytest.mark.parametrize(
    ("start_conversation", "assistant_configuration", "component_coverage", "expected"),
    [
        (
            {"is_nova": True},
            {"feature_flags": {"agent_type": "nova"}},
            {"counts": {"assistant_runtime": 10, "nca": 8, "gmg": 4}},
            "nova",
        ),
        (
            {"is_nova": False},
            {"feature_flags": {"agent_type": "iva"}, "source": "agent_service"},
            {"counts": {"assistant_runtime": 10, "agent_service": 4, "nca": 0}},
            "iva",
        ),
        (
            {"is_nova": False},
            {"feature_flags": {}, "source": None},
            {"counts": {"assistant_runtime": 2, "agent_service": 0, "nca": 0, "gmg": 0}},
            "unknown",
        ),
    ],
)
def test_detect_latency_path_classifies_supported_paths(
    start_conversation: dict, assistant_configuration: dict, component_coverage: dict, expected: str
) -> None:
    assert (
        diagnostic_report._detect_latency_path(
            start_conversation=start_conversation,
            assistant_configuration=assistant_configuration,
            component_coverage=component_coverage,
        )
        == expected
    )


def test_build_latency_segments_and_buckets_from_existing_signals() -> None:
    speech = {
        "srs": {
            "latency": {
                "asr_latency_ms": {"count": 1, "avg_ms": 770.0, "max_ms": 770.0},
                "iva_delivery_latency_ms": {"count": 1, "avg_ms": 1.0, "max_ms": 1.0},
            }
        },
        "sgs": {
            "latency": {
                "ttfc_ms": {"count": 1, "avg_ms": 170.0, "max_ms": 170.0},
                "playback_duration_ms": {"count": 1, "avg_ms": 6460.0, "max_ms": 6460.0},
            }
        },
    }
    turns = [
        {
            "turn_number": 2,
            "duration_ms": 3200.0,
            "ttft_ms": 850.0,
            "latency_breakdown": {"llm_total_ms": 1200.0, "non_llm_ms": 2000.0},
            "tool_calls": [
                {"tool_name": "transfer_call", "status": "failed", "duration_ms": 1500.0},
                {"tool_name": "lookup_customer", "status": "success", "duration_ms": 300.0},
            ],
        }
    ]

    segments = diagnostic_report._build_latency_segments(
        latency_path="nova",
        speech=speech,
        turns=turns,
        component_coverage={"counts": {"assistant_runtime": 10, "nca": 8, "gmg": 6}},
    )
    buckets = diagnostic_report._build_latency_buckets(segments)

    by_name = {segment["segment_name"]: segment for segment in segments}
    assert by_name["srs.asr_compute"]["duration_ms"] == 770.0
    assert by_name["srs.asr_compute"]["bucket"] == "SRS/ASR"
    assert by_name["srs.asr_compute"]["evidence_level"] == "observed"
    assert by_name["llm.total_proxy.turn_2"]["duration_ms"] == 1200.0
    assert by_name["llm.total_proxy.turn_2"]["bucket"] == "GMG/LLM"
    assert by_name["tooling.total.turn_2"]["duration_ms"] == 1800.0
    assert by_name["sgs.playback"]["duration_ms"] == 6460.0

    assert buckets["User/PBX"]["duration_ms"] is None
    assert buckets["assistant_runtime"]["duration_ms"] is None
    assert buckets["NCA orchestration"]["duration_ms"] is None
    assert buckets["SRS/ASR"]["duration_ms"] == 771.0
    assert buckets["GMG/LLM"]["duration_ms"] == 1200.0
    assert buckets["Tooling"]["duration_ms"] == 1800.0
    assert buckets["TTS/playback"]["duration_ms"] == 6630.0


def test_render_markdown_includes_speech_and_turn_latency_sections() -> None:
    rendered = diagnostic_report.render_markdown(
        {
            "session_count": 1,
            "tool_call_count": 1,
            "aggregate": {"contradictions": {"mixed_transfer_outcome_messaging": 1}, "speech_disconnect_events": 2},
            "sessions": [
                {
                    "session_dir": "/tmp/session",
                    "session_id": "s-123",
                    "conversation_id": "c-123",
                    "total_turns": 1,
                    "turns_with_tools": 1,
                    "tool_call_count": 1,
                    "diagnostic_snapshot": {
                        "diagnostic_status": "issue_detected",
                        "confidence": "high",
                        "session_shape": "tooling_session",
                        "trace_completeness": "high",
                        "tool_call_count": 1,
                        "contradiction_count": 1,
                        "error_anomaly_count": 0,
                        "failed_tool_call_count": 0,
                        "has_user_turns": True,
                        "top_signals": ["1 contradiction signal(s) were detected between tool results and final answers."],
                        "key_facts": [
                            "Trace completeness: high",
                            "User turns observed: yes",
                            "Tool calls observed: 1",
                        ],
                    },
                    "basic_judgment": {
                        "diagnostic_status": "issue_detected",
                        "outcome_category": "answer_contradiction",
                        "severity": "high",
                        "owner": "assistant_runtime",
                        "confidence": "high",
                        "customer_impact": "AIR likely answered inconsistently with tool output.",
                        "actionable_now": True,
                        "reported_symptom": "AIR answered wrong",
                        "symptom_assessment": "confirmed",
                    },
                    "ai_diagnosis_report": {
                        "final_verdict": "AIR produced a final answer that likely contradicted successful tool output.",
                        "summary": "The trace contains contradiction evidence in a user turn, and the available component coverage is strong enough to treat this as a likely product issue rather than a logging gap.",
                        "evidence": [
                            "1 contradiction signal(s) were detected between tool results and final answers.",
                            "Trace completeness: high",
                            "User turns observed: yes",
                        ],
                        "gaps": ["No major evidence gaps were detected in the available trace."],
                        "next_actions": [
                            "Inspect the affected turns with toolcall_audit or the turn report to confirm whether AIR ignored or contradicted tool output.",
                        ],
                    },
                    "component_coverage": {
                        "trace_completeness": "high",
                        "counts": {
                            "assistant_runtime": 10,
                            "agent_service": 5,
                            "nca": 8,
                            "cprc_srs": 4,
                            "cprc_sgs": 4,
                            "aig": 0,
                            "gmg": 0,
                        },
                        "missing_components": ["aig", "gmg"],
                    },
                    "start_conversation": {
                        "is_nova": True,
                        "request_id": "req-123",
                        "status": "success",
                        "started_at": "2026-03-23T17:43:19.800Z",
                        "completed_at": "2026-03-23T17:43:19.850Z",
                        "duration_ms": 50.0,
                        "account_id": 2252201020,
                        "conversation_id": "c-123",
                        "assistant_id": "assistant-123",
                        "grpc_address": "dns:///nova",
                    },
                    "session_outcome": {
                        "end_reason": "CallForwarded",
                        "end_timestamp": "2026-03-23T17:44:27.500Z",
                        "close_event": "Conversation close by event: UserDisconnectEvent",
                    },
                    "assistant_configuration": {
                        "source": "agent_service",
                        "assistant_id": "assistant-123",
                        "external_assistant_id": "assistant-123",
                        "configuration_provider_url": "https://intapi.ringcentral.com/ai/iva/...",
                        "application_id": "IVA",
                        "solution": "V1",
                        "group_tag": "gpt52",
                        "voice_id": "voice-1",
                        "languages": ["en-US"],
                        "website": "https://example.com",
                        "tool_names": ["transfer_call"],
                        "tool_count": 1,
                        "raw_enabled_skills": ["knowledgeBase"],
                        "graph_bundle": "multi-agent",
                        "graph_skills": ["KNOWLEDGE_BASE"],
                        "feature_flags": {"hangup_tool_enabled": True},
                        "nca_flag_evaluations": {"nova.nca.llm_request_timeout": '{"enabled":false}'},
                    },
                    "correlation_ids": {
                        "session_id": "s-123",
                        "conversation_id": "c-123",
                        "account_id": 2252201020,
                        "assistant_id": "assistant-123",
                        "external_assistant_id": "assistant-123",
                        "start_conversation_request_id": "req-123",
                        "srs_session_id": "srs-1",
                        "sgs_session_id": "sgs-1",
                        "speech_recognition_request_id": "sr-123",
                        "speech_generation_request_id": "sg-123",
                        "init_completion_id": "init-123",
                        "greeting_completion_id": "greet-123",
                    },
                    "latency_path": "nova",
                    "latency_segments": [
                        {
                            "segment_name": "srs.asr_compute",
                            "bucket": "SRS/ASR",
                            "path": "nova",
                            "owner": "cprc_srs",
                            "evidence_level": "observed",
                            "duration_ms": 770.0,
                            "start_ts": None,
                            "end_ts": None,
                            "source_ref": "speech.srs.latency.asr_latency_ms.avg_ms",
                        },
                        {
                            "segment_name": "llm.total_proxy.turn_2",
                            "bucket": "GMG/LLM",
                            "path": "nova",
                            "owner": "turn_summary",
                            "evidence_level": "derived",
                            "duration_ms": 1200.0,
                            "start_ts": None,
                            "end_ts": None,
                            "source_ref": "turns[0].latency_breakdown.llm_total_ms",
                        },
                    ],
                    "latency_buckets": {
                        "User/PBX": {"duration_ms": None, "segment_count": 0},
                        "SRS/ASR": {"duration_ms": 771.0, "segment_count": 2},
                        "assistant_runtime": {"duration_ms": None, "segment_count": 0},
                        "NCA orchestration": {"duration_ms": None, "segment_count": 0},
                        "GMG/LLM": {"duration_ms": 1200.0, "segment_count": 1},
                        "Tooling": {"duration_ms": 1500.0, "segment_count": 1},
                        "TTS/playback": {"duration_ms": 6630.0, "segment_count": 2},
                    },
                    "manual_rca_view": {
                        "filler_turns": [
                            {
                                "turn_number": 2,
                                "user_transcript": "Transfer me please",
                                "timestamps": {
                                    "matched_interim_timestamp": "2026-03-23T17:43:24.673Z",
                                    "matched_final_timestamp": "2026-03-23T17:43:25.674Z",
                                    "pending_set_timestamp": "2026-03-23T17:43:25.680Z",
                                    "pending_finalize_timestamp": "2026-03-23T17:43:27.996Z",
                                    "request_timestamp": "2026-03-23T17:43:27.996Z",
                                    "nca_filler_ready_timestamp": "2026-03-23T17:43:28.496Z",
                                    "nca_filler_response_start_timestamp": "2026-03-23T17:43:28.918Z",
                                "filler_tts_request_timestamp": "2026-03-23T17:43:28.923Z",
                                "filler_first_chunk_timestamp": "2026-03-23T17:43:29.331Z",
                                "filler_playback_terminal_timestamp": "2026-03-23T17:43:29.651Z",
                                "filler_playback_terminal_state": "finished",
                                "agent_tts_request_timestamp": "2026-03-23T17:43:29.700Z",
                                "agent_first_chunk_timestamp": "2026-03-23T17:43:29.910Z",
                                "agent_playback_start_proxy_timestamp": "2026-03-23T17:43:29.910Z",
                            },
                            "segments_ms": {
                                "srs_matched_interim_to_final_ms": 1001.0,
                                "assistant_runtime_pending_window_ms": 2316.0,
                                "assistant_runtime_request_to_filler_tts_send_ms": 927.0,
                                    "nca_request_to_filler_ready_ms": 500.0,
                                    "nca_filler_ready_to_response_start_ms": 422.0,
                                "nca_filler_race_ms": 406.0,
                                "tts_send_to_first_chunk_ms": 408.0,
                                "filler_playback_terminal_to_agent_playback_start_ms": 259.0,
                                "audible_filler_from_request_ms": 1335.0,
                                "audible_filler_from_matched_interim_ms": 4656.0,
                                "user_speak_end_to_filler_audible_ms": 4656.0,
                                "user_speak_end_to_agent_audible_ms": 5237.0,
                            },
                            }
                        ],
                        "coverage": {},
                    },
                    "layer_diagnostics": [
                        {
                            "layer": "User/PBX",
                            "coverage": "blind",
                            "evidence_level": "blind",
                            "component_count": 0,
                            "key_metrics": {"device_or_pbx_telemetry": "not_observed"},
                            "issue_signals": [],
                            "blind_spots": ["No direct PBX/network/device playback telemetry in saved trace."],
                        },
                        {
                            "layer": "SRS/ASR",
                            "coverage": "observed",
                            "evidence_level": "observed",
                            "component_count": 4,
                            "key_metrics": {
                                "linked": True,
                                "transcript_events": 6,
                                "finalization_pairs": 1,
                                "interim_to_final_avg_ms": 1001.0,
                                "asr_avg_ms": 770.0,
                                "iva_delivery_avg_ms": 1.0,
                                "warning_count": 0,
                                "error_count": 0,
                            },
                            "issue_signals": ["interim->final max=1001 ms"],
                            "blind_spots": [],
                        },
                        {
                            "layer": "assistant_runtime",
                            "coverage": "observed",
                            "evidence_level": "observed",
                            "component_count": 10,
                            "key_metrics": {
                                "request_events": 1,
                                "generation_requests": 1,
                                "filler_ttft_events": 1,
                                "filler_ttft_avg_ms": 927.0,
                                "pending_windows": 1,
                                "pending_window_avg_ms": 2316.0,
                                "turn_error_anomalies": 0,
                            },
                            "issue_signals": ["runtime pending avg=2316 ms"],
                            "blind_spots": [],
                        },
                        {
                            "layer": "NCA orchestration",
                            "coverage": "observed",
                            "evidence_level": "observed",
                            "component_count": 8,
                            "key_metrics": {
                                "filler_race_events": 1,
                                "filler_race_avg_ms": 406.0,
                                "filler_ready_events": 1,
                                "response_start_events": 1,
                                "filler_ready_to_response_start_avg_ms": 422.0,
                                "turn_warning_anomalies": 1,
                            },
                            "issue_signals": ["filler ready->response start avg=422 ms", "nca warnings=1"],
                            "blind_spots": [],
                        },
                    ],
                    "key_timeline": [
                        {"timestamp": "2026-03-23T17:43:19.800Z", "event": "nova_start_requested", "detail": "request_id=req-123"},
                        {"timestamp": "2026-03-23T17:43:19.850Z", "event": "nova_start_completed", "detail": "status=success duration=50 ms"},
                    ],
                    "speech": {
                        "srs": {
                            "expected_session_id": "srs-1",
                            "linked": True,
                            "first_seen": "2026-03-23T17:43:19.862Z",
                            "last_seen": "2026-03-23T17:46:04.005Z",
                            "observed_session_ids": ["srs-1"],
                            "disconnect_events": [
                                {
                                    "timestamp": "2026-03-23T17:46:04.005Z",
                                    "session_id": "srs-1",
                                    "type": "client_disconnected",
                                    "is_error": False,
                                    "message": "Client disconnected",
                                }
                            ],
                            "latency": {
                                "asr_latency_ms": {"count": 1, "avg_ms": 770.0, "max_ms": 770.0},
                                "iva_delivery_latency_ms": {"count": 1, "avg_ms": 1.0, "max_ms": 1.0},
                            },
                        },
                        "sgs": {
                            "expected_session_id": "sgs-1",
                            "linked": True,
                            "first_seen": "2026-03-23T17:43:20.210Z",
                            "last_seen": "2026-03-23T17:44:27.430Z",
                            "observed_session_ids": ["sgs-1"],
                            "disconnect_events": [
                                {
                                    "timestamp": "2026-03-23T17:44:27.430Z",
                                    "session_id": "sgs-1",
                                    "request_id": "sgs-1-12",
                                    "sseq": 12,
                                    "type": "playback_interrupted",
                                    "is_error": False,
                                    "message": "playback interrupted",
                                }
                            ],
                            "request_count": 3,
                            "cancel_count": 1,
                            "last_audio_end": "2026-03-23T17:44:10.801Z",
                            "latency": {
                                "ttfc_ms": {"count": 2, "avg_ms": 170.0, "max_ms": 200.0},
                                "playback_duration_ms": {"count": 2, "avg_ms": 4090.0, "max_ms": 6460.0},
                            },
                            "playback_events": [
                                {
                                    "timestamp": "2026-03-23T17:43:29.651Z",
                                    "request_id": "sgs-1-1",
                                    "sseq": 1,
                                    "state": "finished",
                                    "duration_ms": 728.0,
                                }
                            ],
                        },
                    },
                    "turns": [
                        {
                            "turn_number": 2,
                            "turn_type": "user_turn",
                            "duration_ms": 3200.0,
                            "ttft_ms": 850.0,
                            "latency_breakdown": {"llm_total_ms": 1200.0, "non_llm_ms": 2000.0},
                            "user_transcript": "Transfer me please",
                            "ai_response": "Please hold on.",
                            "tool_calls": [
                                {
                                    "tool_type": "client",
                                    "tool_name": "transfer_call",
                                    "status": "failed",
                                    "duration_ms": 1500.0,
                                    "observed_components": ["assistant_runtime", "nca"],
                                    "tool_type_source": "explicit",
                                    "tool_type_confidence": "high",
                                }
                            ],
                            "contradictions": [
                                {
                                    "severity": "warning",
                                    "type": "mixed_transfer_outcome_messaging",
                                    "message": "mixed message",
                                }
                            ],
                            "anomalies": [],
                        }
                    ],
                }
            ],
        },
        lang="en",
    )

    assert "Final Verdict" in rendered
    assert "Action Summary" in rendered
    assert "Diagnostic Snapshot" in rendered
    assert "Basic Judgment" in rendered
    assert "AI Diagnosis Report" in rendered
    assert "Outcome category: `answer_contradiction`" in rendered
    assert "Reported symptom: `AIR answered wrong`" in rendered
    assert "Component Coverage" in rendered
    assert "Session Outcome" in rendered
    assert "Key Timeline" in rendered
    assert "Recommended Next Actions" in rendered
    assert "Trace completeness: `high`" in rendered
    assert "Contradiction signals: `1`" in rendered
    assert "End reason: `CallForwarded`" in rendered
    assert "Nova / Start Conversation" in rendered
    assert "Assistant Configuration" in rendered
    assert "Correlation IDs" in rendered
    assert "Request ID: `req-123`" in rendered
    assert "Enabled skills: `knowledgeBase`" in rendered
    assert "`speech_generation_request_id`: `sg-123`" in rendered
    assert "Session Scorecard" in rendered
    assert "Customer impact:" in rendered
    assert "Strongest claim: Turn 2 spent 1500 ms in `transfer_call`, but only 259 ms elapsed after filler audio ended." in rendered
    assert "Likely owner: `Tooling`" in rendered
    assert "Attribution confidence: `high`" in rendered
    assert "Next action: Inspect `transfer_call` in turn 2" in rendered
    assert "`long_but_covered`" in rendered
    assert "Turn Summary Matrix" in rendered
    assert "Markers" in rendered
    assert "AI Response" in rendered
    assert "Please hold on." in rendered
    assert "User->Filler Audible" in rendered
    assert "User->Agent Audible" in rendered
    assert "Filler End->Agent Audible" in rendered
    assert "Expanded Timelines" in rendered
    assert "#### Turn 2 (`flagged`)" in rendered
    assert "[SUSPECT] STT lag" in rendered
    assert "- AI: Please hold on." in rendered
    assert "user speak end -> filler audible: 4656 ms" in rendered
    assert "user speak end -> agent audible: 5237 ms" in rendered
    assert "filler audio end -> agent audible: 259 ms" in rendered
    assert "tool: transfer_call" in rendered
    assert "Evidence / Blind Spots" in rendered
    assert "STT lag" in rendered
    assert "derived/proxy" in rendered
    assert "Latency Executive View" in rendered
    assert "Path: `nova`" in rendered
    assert "`SRS/ASR`: duration=771 ms" in rendered
    assert "Latency Segments" in rendered
    assert "`srs.asr_compute`" in rendered
    assert "`llm.total_proxy.turn_2`" in rendered
    assert "Manual RCA View" in rendered
    assert "matched interim -> final: 1001 ms" in rendered
    assert "filler ready -> ResponseStart: 422 ms" in rendered
    assert "audible filler from request: 1335 ms" in rendered
    assert "Layer Diagnostics" in rendered
    assert "`SRS/ASR` coverage=`observed` evidence=`observed`" in rendered
    assert "metrics: linked=true; transcript_events=6; finalization_pairs=1; interim_to_final_avg_ms=1001 ms" in rendered
    assert "`User/PBX` coverage=`blind` evidence=`blind`" in rendered
    assert "blind spots: No direct PBX/network/device playback telemetry in saved trace." in rendered
    assert "Speech Linkage" in rendered
    assert "duration=3200 ms" in rendered
    assert "transfer_call" in rendered
    assert "playback_interrupted" in rendered


def test_render_markdown_defaults_to_zh() -> None:
    rendered = diagnostic_report.render_markdown(
        {
            "session_count": 1,
            "tool_call_count": 0,
            "aggregate": {"contradictions": {}, "speech_disconnect_events": 0},
            "sessions": [
                {
                    "session_dir": "/tmp/session",
                    "session_id": "s-zh",
                    "conversation_id": "c-zh",
                    "total_turns": 1,
                    "turns_with_tools": 0,
                    "tool_call_count": 0,
                    "diagnostic_snapshot": {
                        "diagnostic_status": "short_call",
                        "confidence": "high",
                        "session_shape": "greeting_only",
                        "trace_completeness": "high",
                        "tool_call_count": 0,
                        "contradiction_count": 0,
                        "error_anomaly_count": 0,
                        "failed_tool_call_count": 0,
                        "has_user_turns": False,
                        "top_signals": ["Caller dropped during or immediately after greeting; the session never reached a user turn."],
                        "key_facts": [
                            "Trace completeness: high",
                            "User turns observed: no",
                            "Tool calls observed: 0",
                        ],
                    },
                    "basic_judgment": {
                        "diagnostic_status": "short_call",
                        "outcome_category": "short_call",
                        "severity": "low",
                        "owner": "caller_or_call_flow",
                        "confidence": "high",
                        "customer_impact": "The conversation ended before AIR could handle a real request.",
                        "actionable_now": True,
                        "reported_symptom": "AIR answered wrong",
                        "symptom_assessment": "not_confirmed",
                    },
                    "ai_diagnosis_report": {
                        "final_verdict": "Short call: the session ended with `CallerDropped` before AIR handled a user turn.",
                        "summary": "The trace shows a short call that ended before AIR handled a real user request, so this session does not support diagnosing answer quality or KB usage.",
                        "evidence": ["Caller dropped during or immediately after greeting; the session never reached a user turn."],
                        "gaps": ["No major evidence gaps were detected in the available trace."],
                        "next_actions": [
                            "Use a multi-turn or tool-using session if the goal is to validate AIR reasoning, KB usage, or tool behavior.",
                        ],
                    },
                    "component_coverage": {
                        "trace_completeness": "high",
                        "counts": {"assistant_runtime": 10},
                        "missing_components": [],
                    },
                    "start_conversation": {},
                    "session_outcome": {},
                    "assistant_configuration": {"languages": [], "tool_names": [], "raw_enabled_skills": [], "graph_skills": []},
                    "correlation_ids": {},
                    "key_timeline": [],
                    "speech": {
                        "srs": {
                            "expected_session_id": None,
                            "linked": False,
                            "first_seen": None,
                            "last_seen": None,
                            "observed_session_ids": [],
                            "disconnect_events": [],
                            "latency": {
                                "asr_latency_ms": {"count": 0, "avg_ms": None, "max_ms": None},
                                "iva_delivery_latency_ms": {"count": 0, "avg_ms": None, "max_ms": None},
                            },
                        },
                        "sgs": {
                            "expected_session_id": None,
                            "linked": False,
                            "first_seen": None,
                            "last_seen": None,
                            "observed_session_ids": [],
                            "disconnect_events": [],
                            "request_count": 0,
                            "cancel_count": 0,
                            "last_audio_end": None,
                            "latency": {
                                "ttfc_ms": {"count": 0, "avg_ms": None, "max_ms": None},
                                "playback_duration_ms": {"count": 0, "avg_ms": None, "max_ms": None},
                            },
                        },
                    },
                    "turns": [],
                }
            ],
        }
    )

    assert "# IVA 诊断报告" in rendered
    assert "### 最终结论" in rendered
    assert "### 行动摘要" in rendered
    assert "### 诊断快照" in rendered
    assert "### 会话评分卡" in rendered
    assert "### 基础判断" in rendered
    assert "### AI 诊断报告" in rendered
    assert "结论类别: `short_call`" in rendered
    assert "上报问题: `AIR answered wrong`" in rendered
    assert "短通话：会话在 AIR 处理用户 turn 前以 `CallerDropped` 结束。" in rendered
