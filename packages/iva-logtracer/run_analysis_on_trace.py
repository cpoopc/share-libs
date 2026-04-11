#!/usr/bin/env python3
"""
Run analysis on existing trace files and generate HTML report
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from extractors.iva.turn.analyzer import VoiceCallAnalyzer
from extractors.iva.turn.formatters import generate_html_report

# Session directory
session_dir = Path(__file__).parent / "output" / "iva_session" / "s-a0dd8823671eez19ba983b930zd85c4b0000-b9729947-18e1-4dd9-9011-c2fc916790ff"

if not session_dir.exists():
    print(f"❌ Session directory not found: {session_dir}")
    sys.exit(1)

print(f"📂 Analyzing session in: {session_dir}")

# Initialize Analyzer
analyzer = VoiceCallAnalyzer(session_dir)

# Run Analysis
try:
    print("🧠 Running VoiceCallAnalyzer...")
    report = analyzer.analyze()
    
    print(f"   Turns detected: {len(report.turns)}")
    print(f"   Total duration: {report.total_duration_ms/1000:.2f}s")
    print(f"   Errors found: {len(report.errors)}")

    if not report.turns:
        print("⚠️  Warning: No turns were detected. The report might be empty.")

    # Generate HTML report
    output_path = session_dir / "turn_report.html"
    print(f"🎨 Generating new HTML report...")
    generate_html_report(report, output_path)

    print(f"✅ Report generated: {output_path}")
    print(f"🌐 Open in browser: file://{output_path}")

except Exception as e:
    print(f"❌ Analysis failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
