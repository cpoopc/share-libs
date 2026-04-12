#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json

from logtracer_extractors.kibana_client import KibanaClient
from logtracer_extractors.runtime import (
    get_runtime_diagnostics,
    init_runtime_home,
    load_env_file,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="iva-logtracer")
    subcommands = parser.add_subparsers(dest="command", required=True)

    init = subcommands.add_parser("init")
    init.add_argument("--env", help="Optional named environment, for example production")
    init.add_argument("--force", action="store_true", help="Overwrite the target .env file if it already exists")

    doctor = subcommands.add_parser("doctor")
    doctor.add_argument("--env", help="Optional named environment, for example production")
    doctor.add_argument("--format", choices=["text", "json"], default="text")
    doctor.add_argument(
        "--components",
        action="store_true",
        help="Include static component catalog metadata in doctor output",
    )

    discover = subcommands.add_parser("discover")
    discover.add_argument("--env", required=True)
    discover.add_argument("--last")
    discover.add_argument("--start")
    discover.add_argument("--end")
    discover.add_argument("--field")
    discover.add_argument("--value")
    discover.add_argument("--query")
    discover.add_argument("--index", default="*:*-logs-air_assistant_runtime-*")
    discover.add_argument("--session-key", default="sessionId")
    discover.add_argument("--page-size", type=int, default=500)
    discover.add_argument("--max-pages", type=int, default=50)
    discover.add_argument("--output-dir")
    discover.add_argument("--format", choices=["json", "markdown", "both"], default="both")

    trace = subcommands.add_parser("trace")
    trace.add_argument("id", help="Session ID (s-xxx) or conversation ID")
    trace.add_argument("--env", required=True)
    trace.add_argument("--last", "-l", default="21d")
    trace.add_argument("--loaders", "-L", nargs="+")
    trace.add_argument("--components", "-c", nargs="+", dest="loaders_alias")
    trace.add_argument("--size", "-n", type=int, default=10000)
    trace.add_argument("--format", "-f", choices=["table", "json"], default="json")
    trace.add_argument("--output", "-o")
    trace.add_argument("--no-save", action="store_true")
    trace.add_argument("--save-json", action="store_true")
    trace.add_argument(
        "--explain-components",
        action="store_true",
        help="Include component coverage metadata in the saved trace output",
    )

    turn = subcommands.add_parser("turn")
    turn.add_argument("session_dir", help="Session output directory")
    turn.add_argument("--format", "-f", choices=["table", "markdown", "json"], default="table")
    turn.add_argument("--output", "-o")
    turn.add_argument("--viz", "-v", action="store_true")
    turn.add_argument("--html", action="store_true")

    report = subcommands.add_parser("report")
    report.add_argument("session_dirs", nargs="+", help="Saved iva session output directories")
    report.add_argument("--format", choices=["markdown", "json"], default="markdown")
    report.add_argument("--lang", choices=["zh", "en"], default="zh")
    report.add_argument("--output", "-o")
    report.add_argument("--reported-symptom")

    audit = subcommands.add_parser("audit")
    audit_subcommands = audit.add_subparsers(dest="audit_command", required=True)

    audit_kb = audit_subcommands.add_parser("kb")
    audit_kb.add_argument("trace_dir", help="Path to iva-logtracer output directory")
    audit_kb.add_argument("--tool", default="air_searchCompanyKnowledgeBase")

    audit_tools = audit_subcommands.add_parser("tools")
    audit_tools.add_argument("session_dirs", nargs="+", help="Saved iva session output directories")
    audit_tools.add_argument("--format", choices=["markdown", "json"], default="markdown")
    audit_tools.add_argument("--output", "-o")

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "discover":
        has_query = bool(args.query)
        has_field_value = bool(args.field or args.value)

        if has_query == has_field_value:
            parser.error("Use either --query or --field/--value")
        if bool(args.field) != bool(args.value):
            parser.error("--field and --value must be provided together")
        if args.last and (args.start or args.end):
            parser.error("Use either --last or --start/--end")
        if not args.last and not (args.start and args.end):
            parser.error("Provide --last or both --start and --end")

    return args


def _render_doctor_output(diagnostics: dict[str, object]) -> str:
    required_vars = diagnostics.get("required_vars", {})
    lines = [
        "IVA Logtracer Doctor",
        f"package_root: {diagnostics['package_root']}",
        f"config_root:  {diagnostics['config_root']}",
        f"cache_root:   {diagnostics['cache_root']}",
        f"output_root:  {diagnostics['output_root']}",
        f"env_path:     {diagnostics['env_path']}",
        f"env_exists:   {diagnostics['env_exists']}",
    ]
    if "env_load_error" in diagnostics:
        lines.append(f"env_load_error: {diagnostics['env_load_error']}")
    elif required_vars:
        lines.append("required_vars:")
        for key, present in required_vars.items():
            lines.append(f"  - {key}: {'ok' if present else 'missing'}")
    components = diagnostics.get("components", [])
    if components:
        lines.append("components:")
        for component in components:
            aliases = ", ".join(component["aliases"]) if component["aliases"] else "-"
            candidates = ", ".join(component["index_candidates"]) if component["index_candidates"] else "-"
            resolved = ", ".join(component.get("resolved_indices", [])) if component.get("resolved_indices") else "-"
            status = component.get("status", "not_probed")
            lines.append(
                f"  - {component['name']}: status={status}; aliases={aliases}; "
                f"candidates={candidates}; resolved={resolved}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.command == "init":
        paths = init_runtime_home(force=args.force, env_name=args.env)
        print(f"✅ Config initialized at: {paths['config_root']}")
        print(f"✅ Env file: {paths['env_path']}")
        print(f"✅ Output root: {paths['output_root']}")
        return 0

    if args.command == "doctor":
        diagnostics = get_runtime_diagnostics(args.env)
        if args.components:
            from logtracer_extractors.iva.component_diagnostics import build_component_diagnostics_payload

            probe = False
            client = None
            if diagnostics.get("env_exists") and "env_load_error" not in diagnostics:
                if diagnostics.get("required_vars", {}).get("KIBANA_ES_URL"):
                    client = KibanaClient.from_env()
                    probe = True
            diagnostics["components"] = build_component_diagnostics_payload(client, probe=probe)
        if args.format == "json":
            print(json.dumps(diagnostics, indent=2, ensure_ascii=False, default=str))
        else:
            print(_render_doctor_output(diagnostics))
        return 0

    if args.command == "discover":
        from logtracer_extractors.iva.discovery.command import run_discovery_command

        load_env_file(args.env)
        return run_discovery_command(args)

    if args.command == "trace":
        from logtracer_extractors.iva import session_tracer

        load_env_file(args.env)
        delegated_argv = [
            args.id,
            "--last",
            args.last,
            "--size",
            str(args.size),
            "--format",
            args.format,
        ]
        if args.loaders:
            delegated_argv.extend(["--loaders", *args.loaders])
        if args.loaders_alias:
            delegated_argv.extend(["--components", *args.loaders_alias])
        if args.output:
            delegated_argv.extend(["--output", args.output])
        if args.no_save:
            delegated_argv.append("--no-save")
        if args.save_json:
            delegated_argv.append("--save-json")
        if args.explain_components:
            delegated_argv.append("--explain-components")
        return session_tracer.main(delegated_argv)

    if args.command == "turn":
        from logtracer_extractors.iva.turn import analyzer

        delegated_argv = [args.session_dir, "--format", args.format]
        if args.output:
            delegated_argv.extend(["--output", args.output])
        if args.viz:
            delegated_argv.append("--viz")
        if args.html:
            delegated_argv.append("--html")
        return analyzer.main(delegated_argv)

    if args.command == "report":
        from logtracer_extractors.scripts import diagnostic_report

        delegated_argv = [*args.session_dirs, "--format", args.format, "--lang", args.lang]
        if args.output:
            delegated_argv.extend(["--output", args.output])
        if args.reported_symptom:
            delegated_argv.extend(["--reported-symptom", args.reported_symptom])
        return diagnostic_report.main(delegated_argv)

    if args.command == "audit":
        if args.audit_command == "kb":
            from logtracer_extractors.scripts import kb_tool_audit

            delegated_argv = [args.trace_dir, "--tool", args.tool]
            return kb_tool_audit.main(delegated_argv)

        if args.audit_command == "tools":
            from logtracer_extractors.scripts import toolcall_audit

            delegated_argv = [*args.session_dirs, "--format", args.format]
            if args.output:
                delegated_argv.extend(["--output", args.output])
            return toolcall_audit.main(delegated_argv)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
