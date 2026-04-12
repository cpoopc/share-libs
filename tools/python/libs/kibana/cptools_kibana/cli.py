#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .client import KibanaClient
from .query import get_predefined_query, parse_time_range
from .runtime import APP_NAME, doctor, ensure_layout, load_runtime_env
from .searcher import LogSearcher


ID_FIELDS = {
    "sessionId",
    "conversationId",
    "conversation_id",
    "request_id",
    "srs_session_id",
    "sgs_session_id",
    "accountId",
}


def format_id_query(query: str) -> tuple[str, bool]:
    if len(query) == 36 and query.count("-") == 4:
        return f'conversationId:"{query}"', True

    if query.startswith("s-"):
        return f'sessionId:"{query}"', True

    if ":" in query and '"' not in query:
        field, value = query.split(":", 1)
        if field in ID_FIELDS and value:
            return f'{field}:"{value}"', True

    return query, False


def build_search_query(raw_query: str) -> tuple[str, bool]:
    predefined = get_predefined_query(raw_query)
    if predefined:
        return predefined, False

    return format_id_query(raw_query)


def print_doctor(result: dict[str, Any], output_format: str) -> int:
    if output_format == "json":
        print(json.dumps(result, indent=2))
    else:
        print(f"app: {result['app_name']}")
        print(f"config_root: {result['config_root']}")
        print(f"cache_root: {result['cache_root']}")
        print(f"env_file: {result['env_file']}")
        print(f"selected_env: {result['selected_env']}")
        print("")
        for key, value in result["checks"].items():
            status = "ok" if value else "missing"
            print(f"{key}: {status}")
    return 0 if result["ok"] else 1


def build_client(env_name: str | None, env_file: str | None) -> KibanaClient:
    load_runtime_env(env_name=env_name, env_file=env_file)
    return KibanaClient.from_env()


def cmd_init(args: argparse.Namespace) -> int:
    result = ensure_layout(force=args.force)
    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        print(f"config_root: {result['config_root']}")
        print(f"cache_root: {result['cache_root']}")
        if result["created"]:
            print("created:")
            for path in result["created"]:
                print(f"  - {path}")
        else:
            print("created: none")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    return print_doctor(doctor(env_name=args.env, env_file=args.env_file), args.format)


def cmd_test(args: argparse.Namespace) -> int:
    client = build_client(args.env, args.env_file)
    info = client.test_connection()
    if args.format == "json":
        print(json.dumps(info, indent=2))
    else:
        print("connection: ok")
        print(f"cluster: {info.get('cluster_name', 'unknown')}")
        print(f"version: {info.get('version', {}).get('number', 'unknown')}")
    return 0


def execute_search(
    *,
    query: str,
    env_name: str | None,
    env_file: str | None,
    last: str | None,
    size: int,
    output_format: str,
    output_path: str | None,
    index: str | None,
    count_only: bool,
) -> int:
    client = build_client(env_name, env_file)
    searcher = LogSearcher(client)

    normalized_query, smart_fallback = build_search_query(query)

    if count_only:
        start_time = parse_time_range(last) if last else None
        end_time = "now" if last else None
        count = client.count(
            query=normalized_query,
            index=index,
            start_time=start_time,
            end_time=end_time,
        )
        print(count)
        return 0

    result = searcher.search(
        query=normalized_query,
        index=index,
        last=last,
        size=size,
        smart_fallback=smart_fallback,
    )

    if output_path:
        saved = searcher.export_to_file(result, Path(output_path), output_format)
        print(saved)
        return 0

    if output_format == "json":
        print(searcher.format_json(result))
    elif output_format == "markdown":
        print(searcher.format_markdown(result))
    else:
        print(searcher.format_table(result))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    return execute_search(
        query=args.query,
        env_name=args.env,
        env_file=args.env_file,
        last=args.last,
        size=args.size,
        output_format=args.format,
        output_path=args.output,
        index=args.index,
        count_only=args.count,
    )


def cmd_export(args: argparse.Namespace) -> int:
    return execute_search(
        query=args.query,
        env_name=args.env,
        env_file=args.env_file,
        last=args.last,
        size=args.size,
        output_format=args.format,
        output_path=args.output,
        index=args.index,
        count_only=False,
    )


def cmd_indices(args: argparse.Namespace) -> int:
    client = build_client(args.env, args.env_file)
    indices = sorted(client.get_indices(args.pattern))
    if args.format == "json":
        print(json.dumps(indices, indent=2))
    else:
        for index in indices:
            print(index)
    return 0


def add_env_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--env", "-e", help="Environment name such as lab or production")
    parser.add_argument("--env-file", help="Explicit env file path")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Installed CLI for generic Kibana / Elasticsearch log search")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_init = subparsers.add_parser("init", help="Create XDG config and cache directories")
    p_init.add_argument("--force", action="store_true", help="Overwrite env templates if they already exist")
    p_init.add_argument("--format", choices=("text", "json"), default="text")
    p_init.set_defaults(func=cmd_init)

    p_doctor = subparsers.add_parser("doctor", help="Validate config and credentials")
    add_env_args(p_doctor)
    p_doctor.add_argument("--format", choices=("text", "json"), default="text")
    p_doctor.set_defaults(func=cmd_doctor)

    p_test = subparsers.add_parser("test", help="Test Kibana connectivity")
    add_env_args(p_test)
    p_test.add_argument("--format", choices=("text", "json"), default="text")
    p_test.set_defaults(func=cmd_test)

    p_search = subparsers.add_parser("search", help="Search logs")
    add_env_args(p_search)
    p_search.add_argument("query", help="Lucene/KQL query or predefined query name")
    p_search.add_argument("--last", "-l", help="Relative time range such as 1h, 30m, or 7d")
    p_search.add_argument("--size", "-n", type=int, default=100)
    p_search.add_argument("--format", "-f", choices=("table", "json", "markdown"), default="table")
    p_search.add_argument("--output", "-o", help="Optional output file path")
    p_search.add_argument("--index", "-i", help="Override index pattern")
    p_search.add_argument("--count", action="store_true", help="Only return the count")
    p_search.set_defaults(func=cmd_search)

    p_export = subparsers.add_parser("export", help="Export logs to a file")
    add_env_args(p_export)
    p_export.add_argument("query", help="Lucene/KQL query or predefined query name")
    p_export.add_argument("--last", "-l", help="Relative time range such as 1h, 30m, or 7d")
    p_export.add_argument("--size", "-n", type=int, default=1000)
    p_export.add_argument("--format", "-f", choices=("json", "markdown"), default="json")
    p_export.add_argument("--output", "-o", required=True, help="Output file path")
    p_export.add_argument("--index", "-i", help="Override index pattern")
    p_export.set_defaults(func=cmd_export)

    p_indices = subparsers.add_parser("indices", help="List matching indices")
    add_env_args(p_indices)
    p_indices.add_argument("pattern", nargs="?", default="*", help="Index pattern")
    p_indices.add_argument("--format", "-f", choices=("text", "json"), default="text")
    p_indices.set_defaults(func=cmd_indices)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
