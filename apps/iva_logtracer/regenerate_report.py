#!/usr/bin/env python3
"""
Regenerate HTML report from existing session data using the new template
"""
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from extractors.iva.turn.formatters import generate_html_report

# Session directory
session_dir = Path(__file__).parent / "output" / "iva_session" / "s-a0dd8823671eez19ba983b930zd85c4b0000-b9729947-18e1-4dd9-9011-c2fc916790ff"
summary_file = session_dir / "summary.json"

if not summary_file.exists():
    print(f"❌ Summary file not found: {summary_file}")
    sys.exit(1)

print(f"📂 Loading data from: {summary_file}")

# Load the JSON data
with open(summary_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Import the models to reconstruct the AnalysisReport
from extractors.iva.turn.models import AnalysisReport, CallMetrics, Turn

# Reconstruct CallMetrics
metrics_data = data.get('metrics', {})
metrics = CallMetrics(
    ttft_values=metrics_data.get('ttft_values', []),
    avg_ttft_ms=metrics_data.get('avg_ttft_ms', 0.0),
    interruption_count=metrics_data.get('interruption_count', 0),
    error_count=metrics_data.get('error_count', 0),
    llm_call_count=metrics_data.get('llm_call_count', 0),
    llm_total_latency_ms=metrics_data.get('llm_total_latency_ms', 0.0),
    llm_avg_latency_ms=metrics_data.get('llm_avg_latency_ms', 0.0),
    states_visited=set(metrics_data.get('states_visited', []))
)

# Reconstruct Turns
turns = []
for turn_data in data.get('turns', []):
    turn = Turn(
        turn_number=turn_data.get('turn_number', 0),
        turn_type=turn_data.get('turn_type', ''),
        start_timestamp=turn_data.get('start_timestamp', ''),
        end_timestamp=turn_data.get('end_timestamp', ''),
        duration_ms=turn_data.get('duration_ms', 0.0),
        user_transcript=turn_data.get('user_transcript'),
        user_transcript_confidence=turn_data.get('user_transcript_confidence', 0.0),
        ai_response=turn_data.get('ai_response'),
        ai_phrases=turn_data.get('ai_phrases', []),
        llm_calls=turn_data.get('llm_calls', []),
        tool_calls=turn_data.get('tool_calls', []),
        states=turn_data.get('states', []),
        component_timeline=turn_data.get('component_timeline', []),
        ttft_ms=turn_data.get('ttft_ms'),
        was_interrupted=turn_data.get('was_interrupted', False),
        latency_breakdown=turn_data.get('latency_breakdown', {}),
        anomalies=turn_data.get('anomalies', [])
    )
    turns.append(turn)

# Reconstruct AnalysisReport
report = AnalysisReport(
    session_id=data.get('session_id'),
    conversation_id=data.get('conversation_id'),
    turns=turns,
    metrics=metrics,
    errors=data.get('errors', []),
    warnings=data.get('warnings', []),
    total_turns=data.get('total_turns', 0),
    total_duration_ms=data.get('total_duration_ms', 0.0),
    avg_turn_duration_ms=data.get('avg_turn_duration_ms', 0.0),
    is_completed=data.get('is_completed', False),
    termination_reason=data.get('termination_reason', 'unknown')
)

# Generate new HTML report
output_path = session_dir / "turn_report.html"
print(f"🎨 Generating new HTML report with modern template...")
generate_html_report(report, output_path)

print(f"✅ Report generated: {output_path}")
print(f"🌐 Open in browser: file://{output_path}")
