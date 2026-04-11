from __future__ import annotations

import json

from .models import DiscoveryResult


def render_discovery_json(result: DiscoveryResult) -> str:
    return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)


def render_discovery_markdown(result: DiscoveryResult) -> str:
    payload = result.to_dict()
    query = payload["query"]
    stats = payload["stats"]

    lines = [
        "# Discovery Results",
        "",
        "## Query",
        "",
        f"- env: `{query['env']}`",
        f"- index: `{query['index']}`",
        f"- query_mode: `{query['query_mode']}`",
        f"- session_key: `{query['session_key']}`",
    ]

    time_range = query["time_range"]
    if time_range["last"]:
        lines.append(f"- time_range: last `{time_range['last']}`")
    else:
        lines.append(f"- time_range: `{time_range['start']}` -> `{time_range['end']}`")

    if query["query_mode"] == "field_value":
        lines.append(f"- filter: `{query['field']}` = `{query['value']}`")
    else:
        lines.append(f"- query: `{query['query']}`")

    lines.extend(
        [
        "",
        "## Stats",
        "",
        f"- total_hits: `{stats['total_hits']}`",
        f"- fetched_hits: `{stats['fetched_hits']}`",
        f"- page_size: `{stats['page_size']}`",
        f"- page_count: `{stats['page_count']}`",
        f"- session_count: `{stats['session_count']}`",
        f"- complete: `{stats['complete']}`",
        "",
        "## Sessions",
        "",
        "| sessionId | firstTimestamp | lastTimestamp | logCount | evidence |",
        "| --- | --- | --- | --- | --- |",
        ]
    )

    for session in payload["sessions"]:
        evidence = "; ".join(session.get("evidence", []))
        lines.append(
            f"| {session['sessionId']} | {session['firstTimestamp']} | {session['lastTimestamp']} | {session['logCount']} | {evidence} |"
        )

    return "\n".join(lines)
