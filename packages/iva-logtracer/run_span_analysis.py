#!/usr/bin/env python3
"""
Run span analysis on a session directory
"""
import json
import sys
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent))

from extractors.iva.span.span_correlator import correlate_spans
from extractors.iva.span.span_exporter import export_trace
from extractors.iva.span.span_extractor import extract_spans_from_logs


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_span_analysis.py <session_dir>")
        sys.exit(1)
    
    session_dir = Path(sys.argv[1])
    if not session_dir.exists():
        print(f"Session directory not found: {session_dir}")
        sys.exit(1)
    
    # Component files mapping
    component_files = {
        'assistant_runtime': 'assistant_runtime_trace.json',
        'nca': 'nca_trace.json',
        'aig': 'aig_trace.json',
        'gmg': 'gmg_trace.json',
        'agent_service': 'agent_service_trace.json',
        'cprc_srs': 'cprc_srs_trace.json',
        'cprc_sgs': 'cprc_sgs_trace.json',
    }
    
    # Load logs
    print("📂 Loading logs...")
    logs = {}
    for component, filename in component_files.items():
        file_path = session_dir / filename
        if file_path.exists():
            with open(file_path, 'r') as f:
                data = json.load(f)
                logs[component] = data
                print(f"   {component}: {len(data)} logs")
    
    if not logs:
        print("❌ No logs found!")
        sys.exit(1)
    
    # Get conversation_id and session_id from summary.json
    summary_file = session_dir / 'summary.json'
    conversation_id = None
    session_id = None
    
    if summary_file.exists():
        with open(summary_file, 'r') as f:
            summary = json.load(f)
            conversation_id = summary.get('conversation_id')
            session_id = summary.get('session_id')
    
    if not conversation_id:
        # Try to extract from e2e_trace.json
        e2e_file = session_dir / 'e2e_trace.json'
        if e2e_file.exists():
            with open(e2e_file, 'r') as f:
                e2e = json.load(f)
                conversation_id = e2e.get('conversation_id')
                session_id = e2e.get('session_id')
    
    if not conversation_id:
        print("❌ Could not determine conversation_id")
        sys.exit(1)
    
    print(f"\n📋 Session: {session_id}")
    print(f"📋 Conversation: {conversation_id}")
    
    # Extract spans
    print(f"\n🔬 Extracting spans...")
    spans = extract_spans_from_logs(logs, conversation_id, session_id)
    print(f"   Found {len(spans)} spans")
    
    # Correlate spans
    print(f"🔗 Correlating spans...")
    trace = correlate_spans(spans)
    
    # Statistics
    root_spans = trace.get_root_spans()
    print(f"   Root spans: {len(root_spans)}")
    
    component_summary = trace.get_component_summary()
    if component_summary:
        print(f"   Components: {', '.join(component_summary.keys())}")
    
    critical_path = trace.get_critical_path()
    if critical_path:
        total_critical_ms = sum(s.duration_ms or 0 for s in critical_path)
        print(f"   Critical path: {len(critical_path)} spans, {total_critical_ms:.2f}ms")
    
    # Output directory
    output_dir = session_dir / "span_analysis"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Export
    print(f"\n📤 Exporting trace...")
    formats = ["json", "timeline", "markdown", "chrome_tracing"]
    saved_files = export_trace(trace, output_dir, formats)
    
    for format_name, file_path in saved_files.items():
        print(f"   ✅ {format_name}: {file_path.name}")
    
    print(f"\n📁 Output directory: {output_dir}")
    
    # Print critical path summary
    if critical_path:
        print(f"\n🎯 Critical Path Summary:")
        for span in critical_path[:10]:  # Limit to 10
            duration = f"{span.duration_ms:.2f}ms" if span.duration_ms else "N/A"
            status_emoji = "✅" if span.status.value == "OK" else "❌"
            print(f"   {status_emoji} [{span.component:20}] {span.name:30} {duration:>10}")

if __name__ == "__main__":
    main()

