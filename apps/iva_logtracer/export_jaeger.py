#!/usr/bin/env python3
"""
Export span trace to Jaeger UI JSON format

Usage:
    python export_jaeger.py <session_dir>
    
Example:
    python export_jaeger.py output/iva_session/s-xxx-xxx/span_analysis
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from extractors.iva.span.jaeger_exporter import JaegerExporter
from extractors.iva.span.span_correlator import correlate_spans
from extractors.iva.span.span_extractor import extract_spans_from_logs


def main():
    if len(sys.argv) < 2:
        print("Usage: python export_jaeger.py <session_dir>")
        print("Example: python export_jaeger.py output/iva_session/s-xxx-xxx")
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
    
    # Export to Jaeger format
    print(f"\n📤 Exporting to Jaeger format...")
    exporter = JaegerExporter()
    jaeger_json = exporter.export(trace)
    
    # Output directory
    output_dir = session_dir / "span_analysis"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / "trace_jaeger.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(jaeger_json)
    
    print(f"   ✅ Saved to: {output_file}")
    print(f"\n🎯 To view in Jaeger UI:")
    print(f"   1. Start Jaeger: docker run -d -p 16686:16686 jaegertracing/all-in-one")
    print(f"   2. Open: http://localhost:16686")
    print(f"   3. Click 'JSON File' tab and upload: {output_file}")


if __name__ == "__main__":
    main()

