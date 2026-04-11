#!/usr/bin/env python3

from __future__ import annotations

import argparse

from logtracer_extractors.runtime import load_env_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="iva-logtracer")
    subcommands = parser.add_subparsers(dest="command", required=True)

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

    turn = subcommands.add_parser("turn")
    turn.add_argument("session_dir", help="Session output directory")
    turn.add_argument("--format", "-f", choices=["table", "markdown", "json"], default="table")
    turn.add_argument("--output", "-o")
    turn.add_argument("--viz", "-v", action="store_true")
    turn.add_argument("--html", action="store_true")

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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

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

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
