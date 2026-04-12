from __future__ import annotations

import argparse
import json
import sys

from .fetch_metrics import run_fetch_command
from .runtime import APP_NAME, doctor, ensure_layout, load_runtime_env, resolve_profile
from .core_metrics_daily import run_core_metrics_daily


def _print_json_or_text(payload: dict, output_format: str) -> int:
    if output_format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    for key, value in payload.items():
        if isinstance(value, dict):
            print(f"{key}:")
            for child_key, child_value in value.items():
                print(f"  {child_key}: {child_value}")
        else:
            print(f"{key}: {value}")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    return _print_json_or_text(ensure_layout(force=args.force), args.format)


def cmd_doctor(args: argparse.Namespace) -> int:
    result = doctor(
        env_name=args.env,
        env_file=args.env_file,
        profile_name=args.profile,
        profile_file=args.profile_file,
        real=args.real,
    )
    _print_json_or_text(result, args.format)
    return 0 if result["ok"] else 1


def cmd_resolve_profile(args: argparse.Namespace) -> int:
    load_runtime_env(env_name=args.env, env_file=args.env_file)
    profile = resolve_profile(args.profile, args.profile_file)
    return _print_json_or_text(profile, args.format)


def build_env_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--env", "-e", help="Environment name such as lab or production")
    parser.add_argument("--env-file", help="Explicit env file path")
    return parser


def build_profile_parser() -> argparse.ArgumentParser:
    parser = build_env_parser()
    parser.add_argument("--profile", help="Grafana profile or alias", default="default")
    parser.add_argument("--profile-file", help="Explicit profile aliases YAML path")
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="Installed CLI for Grafana-backed report fetching and core metrics pulls",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_init = subparsers.add_parser("init", help="Create XDG config and cache directories")
    p_init.add_argument("--force", action="store_true")
    p_init.add_argument("--format", choices=("text", "json"), default="text")
    p_init.set_defaults(func=cmd_init)

    p_doctor = subparsers.add_parser("doctor", help="Validate config and optionally test connectivity", parents=[build_profile_parser()])
    p_doctor.add_argument("--format", choices=("text", "json"), default="text")
    p_doctor.add_argument("--real", action="store_true")
    p_doctor.set_defaults(func=cmd_doctor)

    p_profile = subparsers.add_parser("resolve-profile", help="Normalize a profile or alias", parents=[build_profile_parser()])
    p_profile.add_argument("profile", nargs="?", default="default")
    p_profile.add_argument("--format", choices=("text", "json"), default="json")
    p_profile.set_defaults(func=cmd_resolve_profile)

    p_fetch = subparsers.add_parser("fetch", help="Run a config-driven Grafana metrics fetch", parents=[build_env_parser()])
    p_fetch.add_argument("--config", required=True, help="Grafana report config YAML path")
    p_fetch.add_argument("--section", default="all")
    p_fetch.add_argument("--list-panels", action="store_true")
    p_fetch.add_argument("--time-from")
    p_fetch.add_argument("--time-to")
    p_fetch.add_argument("--output", "-o")
    p_fetch.add_argument("--format", choices=("text", "json"), default="text")
    p_fetch.set_defaults(func=run_fetch_command)

    p_daily = subparsers.add_parser("core-metrics-daily", help="Fetch daily core metrics", parents=[build_env_parser()])
    p_daily.add_argument("--config", help="Metrics config YAML path")
    p_daily.add_argument("--day", help="Target day in YYYY-MM-DD format. Defaults to yesterday.")
    p_daily.add_argument("--output-dir", help="Base output directory")
    p_daily.add_argument("--stdout-format", choices=("text", "json"), default="text")
    p_daily.set_defaults(func=run_core_metrics_daily)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv or sys.argv[1:]))
    load_runtime_env(env_name=getattr(args, "env", None), env_file=getattr(args, "env_file", None))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
