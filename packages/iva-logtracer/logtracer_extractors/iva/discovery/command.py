from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ...kibana_client import KibanaClient, parse_time_range
from .models import DiscoveryRequest, DiscoveryResult, DiscoveryStats
from .renderers import render_discovery_json, render_discovery_markdown
from .service import aggregate_sessions, fetch_all_hits


def run_discovery_command(args) -> int:
    start_time, end_time = _resolve_time_range(args)
    request = DiscoveryRequest(
        env=args.env,
        index=args.index,
        field=args.field,
        value=args.value,
        query=args.query,
        session_key=args.session_key,
        page_size=args.page_size,
        max_pages=args.max_pages,
        start_time=start_time,
        end_time=end_time,
    )

    client = KibanaClient.from_env()
    query = args.query or f'{args.field}:"{args.value}"'
    paged_hits = fetch_all_hits(
        client=client,
        query=query,
        index=args.index,
        start_time=start_time,
        end_time=end_time,
        page_size=args.page_size,
        max_pages=args.max_pages,
    )
    sessions = aggregate_sessions(
        hits=paged_hits.hits,
        session_key=args.session_key,
        matched_field_name=args.field,
    )
    result = DiscoveryResult(
        query=request,
        stats=DiscoveryStats(
            total_hits=paged_hits.total_hits,
            fetched_hits=len(paged_hits.hits),
            page_size=args.page_size,
            page_count=paged_hits.page_count,
            session_count=len(sessions),
            complete=_is_complete_result(
                total_hits=paged_hits.total_hits,
                fetched_hits=len(paged_hits.hits),
                page_count=paged_hits.page_count,
                max_pages=args.max_pages,
            ),
        ),
        sessions=sessions,
    )

    output_dir = _resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.format in {"json", "both"}:
        (output_dir / "discovery_results.json").write_text(
            render_discovery_json(result),
            encoding="utf-8",
        )
    if args.format in {"markdown", "both"}:
        (output_dir / "discovery_results.md").write_text(
            render_discovery_markdown(result),
            encoding="utf-8",
        )

    return 0


def _resolve_time_range(args) -> tuple[str | None, str | None]:
    if args.last:
        return parse_time_range(args.last), "now"
    return args.start, args.end


def _resolve_output_dir(output_dir: str | None) -> Path:
    if output_dir:
        return Path(output_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path.cwd() / "output" / "discovery" / timestamp


def _is_complete_result(
    *,
    total_hits: int,
    fetched_hits: int,
    page_count: int,
    max_pages: int,
) -> bool:
    if fetched_hits >= total_hits:
        return True
    if page_count >= max_pages:
        return False
    return False
