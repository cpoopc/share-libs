from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

import requests

from .models import EpicRequest, ImportRequest, PullRequest, PushRequest, ShowRequest, SprintRequest, StatusRequest
from .runtime import (
    bootstrap_workspace,
    get_runtime_diagnostics,
    init_runtime_home,
    prepare_cli_environment,
    resolve_workspace_paths,
)
from .service import JiraTicketSyncService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jira-ticket-sync")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--env", help="Optional environment suffix such as production or lab")
    init_parser.add_argument("--force", action="store_true")

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--env", help="Optional environment suffix such as production or lab")
    doctor_parser.add_argument("--format", choices=("json", "text"), default="text")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("path")

    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("ticket")
    show_parser.add_argument("--real", action="store_true")
    show_parser.add_argument("--profile")
    show_parser.add_argument("--jira-project-config")

    push_parser = subparsers.add_parser("push")
    push_parser.add_argument("path")
    push_parser.add_argument("--dry-run", action="store_true")
    push_parser.add_argument("--real", action="store_true")
    push_parser.add_argument("--profile-root")
    push_parser.add_argument("--state-file")
    push_parser.add_argument("--jira-project-config")

    pull_parser = subparsers.add_parser("pull")
    pull_parser.add_argument("path")
    pull_parser.add_argument("--dry-run", action="store_true")
    pull_parser.add_argument("--real", action="store_true")
    pull_parser.add_argument("--profile-root")
    pull_parser.add_argument("--state-file")
    pull_parser.add_argument("--jira-project-config")

    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("tickets", nargs="+")
    import_parser.add_argument("--dry-run", action="store_true")
    import_parser.add_argument("--real", action="store_true")
    import_parser.add_argument("--profile")
    import_parser.add_argument("--field-classification-cache")
    import_parser.add_argument("--field-classification-root")
    import_parser.add_argument("--jira-project-config")

    sprint_parser = subparsers.add_parser("sprints")
    sprint_parser.add_argument("--project", required=True)
    sprint_parser.add_argument("--board-id", type=int)
    sprint_parser.add_argument("--state", default="active,future")
    sprint_parser.add_argument("--name-prefix")
    sprint_parser.add_argument("--real", action="store_true")
    sprint_parser.add_argument("--jira-project-config")

    epic_parser = subparsers.add_parser("epics")
    epic_parser.add_argument("--project", required=True)
    epic_parser.add_argument("--team")
    epic_parser.add_argument("--active-only", action="store_true")
    epic_parser.add_argument("--max-results", type=int, default=20)
    epic_parser.add_argument("--real", action="store_true")
    epic_parser.add_argument("--profile")
    epic_parser.add_argument("--jira-project-config")

    resolve_paths_parser = subparsers.add_parser("resolve-paths")
    resolve_paths_parser.add_argument("--workspace-root")
    resolve_paths_parser.add_argument("--manifest-root")
    resolve_paths_parser.add_argument("--profile-root")
    resolve_paths_parser.add_argument("--template-root")
    resolve_paths_parser.add_argument("--project-config")
    resolve_paths_parser.add_argument("--state-file")
    resolve_paths_parser.add_argument("--field-classification-root")
    resolve_paths_parser.add_argument("--format", choices=("json", "text"), default="json")

    bootstrap_parser = subparsers.add_parser("bootstrap-workspace")
    bootstrap_parser.add_argument("--target", required=True)
    bootstrap_parser.add_argument("--force", action="store_true")
    bootstrap_parser.add_argument("--dry-run", action="store_true")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    raw_args = list(argv) if argv is not None else list(sys.argv[1:])

    try:
        prepared_args = prepare_cli_environment(raw_args)
    except ValueError as exc:
        print(str(exc))
        return 2

    parser = build_parser()
    args = parser.parse_args(prepared_args)
    service = JiraTicketSyncService()

    try:
        if args.command == "init":
            paths = init_runtime_home(force=args.force, env_name=args.env)
            return _render_init(paths)
        if args.command == "doctor":
            diagnostics = get_runtime_diagnostics(args.env)
            return _render_doctor(diagnostics, args.format)
        if args.command == "status":
            return _render_status(service.status(StatusRequest(path=Path(args.path))))
        if args.command == "show":
            if not args.real:
                print("show requires --real")
                return 2
            return _render_show(
                service.show_issue(
                    ShowRequest(
                        ticket=args.ticket,
                        use_real=args.real,
                        profile_path=Path(args.profile) if args.profile else None,
                        jira_project_config_path=Path(args.jira_project_config) if args.jira_project_config else None,
                    )
                )
            )
        if args.command == "push":
            return _render_push(
                service.push(
                    PushRequest(
                        path=Path(args.path),
                        dry_run=args.dry_run,
                        use_real=args.real,
                        profile_root=Path(args.profile_root) if args.profile_root else None,
                        state_file=Path(args.state_file) if args.state_file else None,
                        jira_project_config_path=Path(args.jira_project_config) if args.jira_project_config else None,
                    )
                ),
                dry_run=args.dry_run,
            )
        if args.command == "pull":
            return _render_pull(
                service.pull(
                    PullRequest(
                        path=Path(args.path),
                        dry_run=args.dry_run,
                        use_real=args.real,
                        profile_root=Path(args.profile_root) if args.profile_root else None,
                        state_file=Path(args.state_file) if args.state_file else None,
                        jira_project_config_path=Path(args.jira_project_config) if args.jira_project_config else None,
                    )
                )
            )
        if args.command == "import":
            return _render_import(
                service.import_issues(
                    ImportRequest(
                        tickets=list(args.tickets),
                        dry_run=args.dry_run,
                        use_real=args.real,
                        profile_path=Path(args.profile) if args.profile else None,
                        field_classification_cache_path=Path(args.field_classification_cache)
                        if args.field_classification_cache
                        else None,
                        field_classification_root=Path(args.field_classification_root)
                        if args.field_classification_root
                        else None,
                        jira_project_config_path=Path(args.jira_project_config) if args.jira_project_config else None,
                    )
                )
            )
        if args.command == "sprints":
            return _render_sprints(
                service.list_sprints(
                    SprintRequest(
                        project_key=args.project,
                        board_id=args.board_id,
                        state=args.state,
                        name_prefix=args.name_prefix,
                        use_real=args.real,
                        jira_project_config_path=Path(args.jira_project_config) if args.jira_project_config else None,
                    )
                )
            )
        if args.command == "epics":
            return _render_epics(
                service.list_epics(
                    EpicRequest(
                        project_key=args.project,
                        team_key=args.team,
                        active_only=args.active_only,
                        max_results=args.max_results,
                        use_real=args.real,
                        profile_path=Path(args.profile) if args.profile else None,
                        jira_project_config_path=Path(args.jira_project_config) if args.jira_project_config else None,
                    )
                )
            )
        if args.command == "resolve-paths":
            paths = resolve_workspace_paths(
                workspace_root=args.workspace_root,
                manifest_root=args.manifest_root,
                profile_root=args.profile_root,
                template_root=args.template_root,
                project_config=args.project_config,
                state_file=args.state_file,
                field_classification_root=args.field_classification_root,
            )
            return _render_resolve_paths(paths, args.format)
        if args.command == "bootstrap-workspace":
            for message in bootstrap_workspace(args.target, force=args.force, dry_run=args.dry_run):
                print(message)
            return 0
    except (requests.exceptions.RequestException, ImportError, ValueError) as exc:
        if getattr(args, "real", False):
            print(f"Real Jira backend failed: {exc}")
            return 2
        raise

    parser.print_help()
    return 1


def _render_status(result) -> int:
    for item in result.items:
        print(f"{item.local_id}: {item.status}")
    return 0


def _render_init(paths: dict[str, Path]) -> int:
    print(f"Config initialized at: {paths['config_root']}")
    print(f"Workspace root: {paths['workspace_root']}")
    print(f"Env file: {paths['env_path']}")
    print(f"Cache root: {paths['cache_root']}")
    print(f"Output root: {paths['output_root']}")
    return 0


def _render_doctor(diagnostics: dict[str, object], output_format: str) -> int:
    if output_format == "json":
        print(json.dumps(diagnostics, indent=2, ensure_ascii=False, default=str))
        return 0

    lines = [
        "jira-ticket-sync Doctor",
        f"config_root:              {diagnostics['config_root']}",
        f"workspace_root:           {diagnostics['workspace_root']}",
        f"cache_root:               {diagnostics['cache_root']}",
        f"output_root:              {diagnostics['output_root']}",
        f"env_path:                 {diagnostics['env_path']}",
        f"env_exists:               {diagnostics['env_exists']}",
        f"project_config:           {diagnostics['project_config']}",
        f"uses_packaged_workspace:  {diagnostics['uses_packaged_workspace']}",
    ]
    missing = diagnostics.get("missing_env_vars") or []
    placeholders = diagnostics.get("placeholder_env_vars") or []
    if missing:
        lines.append(f"missing_env_vars:         {', '.join(missing)}")
    if placeholders:
        lines.append(f"placeholder_env_vars:     {', '.join(placeholders)}")
    print("\n".join(lines))
    return 0


def _render_show(result) -> int:
    print(f"Key: {result.ticket}")
    print(f"Project: {result.project_key}")
    for key in ("issue_type", "status", "priority", "assignee"):
        value = result.summary.get(key)
        if value:
            print(f"{key.replace('_', ' ').title()}: {value}")
    labels = result.summary.get("labels")
    if labels:
        print(f"Labels: {', '.join(labels)}")
    summary = result.summary.get("summary")
    if summary:
        print(f"Summary: {summary}")
    description = result.summary.get("description")
    if description:
        print("Description:")
        print(description)
    custom_fields = result.summary.get("fields", {})
    if custom_fields:
        print("Fields:")
        for field_name, value in custom_fields.items():
            print(f"  {field_name}: {value}")
    return 0


def _render_push(result, *, dry_run: bool) -> int:
    prefix = "DRY-RUN " if dry_run else ""
    for action in result.actions:
        if action.jira_key:
            print(f"{action.action} {action.local_id} -> {action.jira_key}")
        else:
            print(f"{prefix}{action.action} {action.local_id}")
        if action.dropped_fields:
            print(f"WARN {action.local_id} dropped_fields={','.join(action.dropped_fields)}")
        if action.follow_up_error:
            print(f"WARN {action.local_id} follow_up_error={action.follow_up_error}")
    return 0


def _render_pull(result) -> int:
    for action in result.actions:
        prefix = "DRY-RUN " if action.dry_run else ""
        print(f"{prefix}PULL {action.local_id} <- {action.jira_key}")
    return 0


def _render_import(result) -> int:
    prefix = "DRY-RUN " if result.dry_run else ""
    print(f"{prefix}IMPORT sources: {', '.join(result.tickets)}")
    if result.classification_path is not None:
        print(f"{prefix}IMPORT field classification cache: {result.classification_path}")
    print(
        f"{prefix}IMPORT summary: "
        f"confirmed={len(result.template.get('confirmed_fields', []))}, "
        f"candidate={len(result.template.get('candidate_fields', []))}, "
        f"review={len(result.template.get('review_queue', []))}, "
        f"ignored={len(result.template.get('ignored_fields', []))}"
    )
    print(result.template)
    return 0


def _render_sprints(result) -> int:
    for sprint in result.sprints:
        print(f"{sprint['id']}\t{sprint.get('state', '')}\t{sprint.get('name', '')}")
    return 0


def _render_epics(result) -> int:
    for epic in result.epics:
        print(f"{epic['key']}\t{epic.get('status', '')}\t{epic.get('summary', '')}\t{epic.get('url', '')}")
    return 0


def _render_resolve_paths(paths: dict[str, Path], output_format: str) -> int:
    if output_format == "json":
        print(json.dumps({key: str(value) for key, value in paths.items()}, indent=2, sort_keys=True))
        return 0

    for key, value in paths.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
