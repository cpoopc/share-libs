#!/usr/bin/env python3
"""Debug span duration after fix"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from extractors.iva.span.span_correlator import correlate_spans
from extractors.iva.span.span_extractor import extract_spans_from_logs

session_dir = Path(__file__).parent / 'output/iva_session/s-a7860201cfd2dz19b6b5ad7daz59c66c80000-c7b8b6fe-a5fa-4151-89d6-51782bf08e23'

component_files = {
    'assistant_runtime': 'assistant_runtime_trace.json',
    'nca': 'nca_trace.json',
    'aig': 'aig_trace.json',
    'gmg': 'gmg_trace.json',
    'agent_service': 'agent_service_trace.json',
    'cprc_srs': 'cprc_srs_trace.json',
    'cprc_sgs': 'cprc_sgs_trace.json',
}

logs = {}
for component, filename in component_files.items():
    file_path = session_dir / filename
    if file_path.exists():
        with open(file_path, 'r') as f:
            logs[component] = json.load(f)

with open(session_dir / 'summary.json', 'r') as f:
    summary = json.load(f)
    conversation_id = summary.get('conversation_id')
    session_id = summary.get('session_id')

spans = extract_spans_from_logs(logs, conversation_id, session_id)
trace = correlate_spans(spans)

zero_duration = 0
negative_duration = 0
positive_duration = 0
none_duration = 0

for span in trace.spans:
    if span.duration_ms is None:
        none_duration += 1
    elif span.duration_ms < 0:
        negative_duration += 1
    elif span.duration_ms == 0:
        zero_duration += 1
    else:
        positive_duration += 1

print(f"Total spans: {len(trace.spans)}")
print(f"None duration (unfinished): {none_duration}")
print(f"Zero duration: {zero_duration}")
print(f"Negative duration: {negative_duration}")
print(f"Positive duration: {positive_duration}")

print("\n--- Spans with positive duration ---")
for span in trace.spans:
    if span.duration_ms and span.duration_ms > 0:
        print(f"  [{span.component:20}] {span.name:35} {span.duration_ms:>10.2f}ms")

