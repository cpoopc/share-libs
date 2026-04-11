#!/usr/bin/env python3

import argparse


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

        return run_discovery_command(args)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
