"""Config-driven Grafana metrics fetching helpers."""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .config_loader import load_config
from .grafana_extractor import GrafanaExtractor
from .grafana_utils import get_grafana_client


def list_panels_for_section(config: dict[str, Any], section_name: str) -> int:
    section = config.get(section_name)
    if not section:
        print(f"❌ Section '{section_name}' not found in config")
        return 1

    source_key = section.get("source")
    source_config = config.get("grafana_sources", {}).get(source_key)

    if not source_config:
        print(f"❌ Grafana source '{source_key}' not found")
        return 1

    print(f"\n📊 {section_name.upper()} - {source_config['name']}")
    print(f"   Dashboard: {section.get('dashboard_uid')}")
    print(f"   URL: {section.get('dashboard_url')}")
    print()
    
    try:
        client = get_grafana_client(source_config)
        if not client.test_connection():
            return 1

        panels = client.list_panels(section["dashboard_uid"])
        print(f"Found {len(panels)} panels:\n")
        for p in panels:
            indent = "  " if p["type"] == "row" else "    "
            print(f"{indent}[{p['id']:3}] {p['title']} ({p['type']})")
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    return 0


def format_value(value: float, fmt: str) -> str:
    """格式化数值"""
    if fmt == "duration":
        if value < 1:
            return f"{value * 1000:.0f}ms"
        return f"{value:.2f}s"
    elif fmt == "percent":
        return f"{value:.2f}%"
    return f"{value:.2f}"


def fetch_section_data(
    config: dict[str, Any],
    section_name: str,
    time_from: str | None = None,
    time_to: str | None = None,
) -> dict[str, Any]:
    section = config.get(section_name)
    if not section:
        print(f"❌ Section '{section_name}' not found in config")
        return {}

    source_key = section.get("source")
    source_config = config.get("grafana_sources", {}).get(source_key, {})

    print(f"\n{'='*60}")
    print(f"📊 {section_name.upper()} - {source_config.get('name', 'Unknown')}")
    print(f"   Time: {time_from or section.get('time_from', 'now-7d')} to {time_to or section.get('time_to', 'now')}")
    print(f"   Dashboard: {section.get('dashboard_uid')}")
    print("="*60)

    try:
        extractor = GrafanaExtractor(source_config)
        if not extractor.client.test_connection():
            return {}
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return {}

    return extractor.extract_section(
        section_config=section,
        grafana_sources=config.get("grafana_sources", {}),
        time_from=time_from,
        time_to=time_to,
    )


def generate_report(
    all_results: dict[str, dict[str, Any]],
    config: dict[str, Any],
    time_from: str,
    time_to: str,
) -> str:
    lines = [
        "# Weekly Metrics Report",
        "",
        f"**Time Range**: {time_from} to {time_to}",
        f"**Generated**: {datetime.now().isoformat()}",
        "",
    ]

    for section_name, section_results in all_results.items():
        section_config = config.get(section_name, {})
        dashboard_url = section_config.get("dashboard_url", "")

        lines.append(f"## {section_name.replace('_', ' ').title()}")
        lines.append("")
        if dashboard_url:
            lines.append(f"**Dashboard**: [{section_config.get('dashboard_uid')}]({dashboard_url})")
            lines.append("")

        lines.append("| Metric | Average |")
        lines.append("|--------|---------|")

        for name, result in section_results.items():
            value = result.get("value")
            fmt = result.get("format", "percent")
            status = format_value(value, fmt) if value is not None else "N/A"
            lines.append(f"| {name} | {status} |")

        lines.append("")

    return "\n".join(lines)


def run_fetch_command(args) -> int:
    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"❌ Failed to load config: {e}")
        return 1

    all_sections = [k for k in config.keys() if k not in ["name", "description", "output", "slides", "variables", "grafana_sources"]]

    if args.list_panels:
        sections = all_sections if args.section == "all" else [args.section]
        exit_code = 0
        for section in sections:
            exit_code = max(exit_code, list_panels_for_section(config, section))
        return exit_code

    sections = all_sections if args.section == "all" else [args.section]
    all_results = {}

    for section in sections:
        results = fetch_section_data(config, section, args.time_from, args.time_to)
        if results:
            all_results[section] = results

    # JSON 输出
    if args.format == "json":
        json_output = {}
        for section_name, section_results in all_results.items():
            json_output[section_name] = {}
            for name, result in section_results.items():
                json_output[section_name][name] = {
                    "value": result.get("value"),
                    "formatted": format_value(result.get("value", 0), result.get("format", "percent"))
                    if result.get("value") is not None
                    else None,
                    "min": result.get("min"),
                    "formatted_min": format_value(result.get("min", 0), result.get("format", "percent"))
                    if result.get("min") is not None
                    else None,
                    "max": result.get("max"),
                    "formatted_max": format_value(result.get("max", 0), result.get("format", "percent"))
                    if result.get("max") is not None
                    else None,
                    "format": result.get("format"),
                    "unit": "s" if result.get("format") == "duration" else ("%" if result.get("format") == "percent" else ""),
                }
        json_str = json.dumps(json_output, indent=2, ensure_ascii=False)
        print(json_str)

        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json_str + "\n", encoding="utf-8")
            print(f"\n📝 JSON saved to: {output_path}", file=sys.stderr)
        return 0

    print("\n" + "="*60)
    print("📋 Summary")
    print("="*60)

    for section_name, section_results in all_results.items():
        print(f"\n{section_name.upper()}:")
        for name, result in section_results.items():
            value = result.get("value")
            fmt = result.get("format", "percent")
            status = format_value(value, fmt) if value is not None else "N/A"
            print(f"  {name}: {status}")

    # 保存报告
    if args.output:
        time_from = args.time_from or "now-7d"
        time_to = args.time_to or "now"
        report = generate_report(all_results, config, time_from, time_to)

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report + "\n", encoding="utf-8")

        print(f"\n📝 Report saved to: {output_path}")
    return 0


__all__ = [
    "fetch_section_data",
    "format_value",
    "generate_report",
    "list_panels_for_section",
    "run_fetch_command",
]
