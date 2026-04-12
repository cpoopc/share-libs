from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

import html2text

from cptools_confluence import ConfluenceClient, SyncConfig, get_client_from_env

from .runtime import APP_NAME, doctor, ensure_layout, load_runtime_env, resolve_config_file


def print_json_or_text(payload: dict, output_format: str) -> int:
    if output_format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for key, value in payload.items():
            if isinstance(value, dict):
                print(f"{key}:")
                for child_key, child_value in value.items():
                    status = "ok" if child_value else "missing"
                    print(f"  {child_key}: {status}")
            else:
                print(f"{key}: {value}")
    return 0


@contextmanager
def forwarded_argv(program: str, args: list[str]):
    original = sys.argv[:]
    sys.argv = [program, *args]
    try:
        yield
    finally:
        sys.argv = original


def ensure_config_arg(raw_args: list[str]) -> list[str]:
    if "--config" in raw_args or "-c" in raw_args:
        return raw_args
    return ["--config", str(resolve_config_file()), *raw_args]


def dispatch_to(module_main: Callable[[], None], program: str, raw_args: list[str], *, with_config: bool = False) -> int:
    final_args = ensure_config_arg(raw_args) if with_config else raw_args
    with forwarded_argv(program, final_args):
        module_main()
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    return print_json_or_text(ensure_layout(force=args.force), args.format)


def build_configured_client(config_file: str | None = None) -> ConfluenceClient:
    config_path = resolve_config_file(config_file)
    if config_path.exists():
        config = SyncConfig.from_yaml(str(config_path))
        return ConfluenceClient(
            base_url=config.confluence_url,
            username=config.auth.username,
            api_token=config.auth.token,
            use_bearer_token=config.auth.use_bearer,
        )
    return get_client_from_env(load_env=False)


def cmd_doctor(args: argparse.Namespace) -> int:
    result = doctor(
        env_name=args.env,
        env_file=args.env_file,
        config_file=args.config,
    )

    if args.real and result["ok"]:
        try:
            client = build_configured_client(args.config)
            connection_ok = client.test_connection()
            result["checks"]["connection_test"] = connection_ok
            if connection_ok and args.page_id:
                result["page_title"] = client.get_page_by_id(args.page_id, expand="version").get("title", "")
            if connection_ok and args.parent:
                result["parent_title"] = client.get_page_by_id(args.parent, expand="version").get("title", "")
            if args.space:
                result["target_space"] = args.space
                result["space_permission_note"] = "Create permission can only be confirmed by a real create/update."
            result["ok"] = result["ok"] and connection_ok
        except Exception as exc:
            result["checks"]["connection_test"] = False
            result["connection_error"] = str(exc)
            result["ok"] = False

    code = 0 if result["ok"] else 1
    print_json_or_text(result, args.format)
    return code


def cmd_search(raw_args: list[str]) -> int:
    from searchers.cql_search import main as search_main

    return dispatch_to(search_main, "confluence-sync search", raw_args)


def cmd_extract(raw_args: list[str]) -> int:
    normalized_args = list(raw_args)
    if normalized_args and normalized_args[0] in {"markdown", "md"}:
        normalized_args = normalized_args[1:]
        from extractors.images_extractor import main as extract_main

        return dispatch_to(extract_main, "confluence-sync extract", normalized_args, with_config=True)

    if normalized_args and normalized_args[0] == "pdf":
        normalized_args = normalized_args[1:]
        from extractors.pdf_exporter import main as extract_main

        return dispatch_to(extract_main, "confluence-sync extract", normalized_args, with_config=True)

    if normalized_args and normalized_args[0] == "test":
        normalized_args = ["--test", *normalized_args[1:]]

    from extractors.images_extractor import main as extract_main

    return dispatch_to(extract_main, "confluence-sync extract", normalized_args, with_config=True)


def cmd_fetch(raw_args: list[str]) -> int:
    if not raw_args or raw_args[0] in {"-h", "--help"}:
        print("Usage: confluence-sync fetch <page_id>")
        return 0

    client = get_client_from_env(load_env=False)
    page = client.get_page_by_id(raw_args[0], expand="body.storage")
    if not page:
        print("Page not found", file=sys.stderr)
        return 1

    html = page.get("body", {}).get("storage", {}).get("value", "")
    renderer = html2text.HTML2Text()
    renderer.ignore_links = False
    renderer.body_width = 0
    print(renderer.handle(html))
    return 0


def cmd_upload(raw_args: list[str]) -> int:
    if "--openapi" in raw_args:
        from uploaders.openapi_uploader import main as upload_main
    else:
        from uploaders.markdown_uploader import main as upload_main

    return dispatch_to(upload_main, "confluence-sync upload", raw_args, with_config=True)


def cmd_translate(raw_args: list[str]) -> int:
    from extractors.page_translator import main as translate_main

    return dispatch_to(translate_main, "confluence-sync translate", raw_args, with_config=True)


def cmd_bootstrap(args: argparse.Namespace) -> int:
    result = ensure_layout(force=args.force)
    result["note"] = "install.sh already installs Python dependencies. Install mmdc separately if you need rendered Mermaid output."
    return print_json_or_text(result, args.format)


def build_meta_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--env", "-e", help="Environment name such as lab or production")
    parser.add_argument("--env-file", help="Explicit env file path")
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="Installed CLI for Confluence search, extraction, upload, and translation",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_init = subparsers.add_parser("init", help="Create XDG config and cache directories")
    p_init.add_argument("--force", action="store_true")
    p_init.add_argument("--format", choices=("text", "json"), default="text")
    p_init.set_defaults(func=cmd_init)

    p_bootstrap = subparsers.add_parser("bootstrap", help="Alias for init plus setup guidance")
    p_bootstrap.add_argument("--force", action="store_true")
    p_bootstrap.add_argument("--format", choices=("text", "json"), default="text")
    p_bootstrap.set_defaults(func=cmd_bootstrap)

    p_doctor = subparsers.add_parser("doctor", help="Validate config and optionally test connectivity", parents=[build_meta_parser()])
    p_doctor.add_argument("--format", choices=("text", "json"), default="text")
    p_doctor.add_argument("--real", action="store_true", help="Also test Confluence connectivity")
    p_doctor.add_argument("--config", help="Explicit config.yaml path")
    p_doctor.add_argument("--page-id", help="Optional page id to verify read access")
    p_doctor.add_argument("--space", help="Optional target space for create/update notes")
    p_doctor.add_argument("--parent", help="Optional parent page id to verify read access")
    p_doctor.set_defaults(func=cmd_doctor)

    return parser


def parse_forwarded_meta_args(raw_args: list[str]) -> tuple[str | None, str | None, list[str]]:
    env_name: str | None = None
    env_file: str | None = None
    forwarded: list[str] = []
    i = 0
    while i < len(raw_args):
        current = raw_args[i]
        if current in {"--env", "-e"} and i + 1 < len(raw_args):
            env_name = raw_args[i + 1]
            i += 2
            continue
        if current == "--env-file" and i + 1 < len(raw_args):
            env_file = raw_args[i + 1]
            i += 2
            continue
        forwarded.extend(raw_args[i:])
        break
    return env_name, env_file, forwarded


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(argv or sys.argv[1:])
    if raw_argv and raw_argv[0] in {"search", "extract", "fetch", "upload", "translate"}:
        command = raw_argv[0]
        env_name, env_file, forwarded_args = parse_forwarded_meta_args(raw_argv[1:])
        load_runtime_env(env_name=env_name, env_file=env_file)
        if command == "search":
            return cmd_search(forwarded_args)
        if command == "extract":
            return cmd_extract(forwarded_args)
        if command == "fetch":
            return cmd_fetch(forwarded_args)
        if command == "upload":
            return cmd_upload(forwarded_args)
        return cmd_translate(forwarded_args)

    parser = build_parser()
    args = parser.parse_args(raw_argv)
    load_runtime_env(env_name=getattr(args, "env", None), env_file=getattr(args, "env_file", None))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
