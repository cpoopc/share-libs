from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import DiscoverySession


DISCOVERY_SORT = [{"@timestamp": {"order": "asc"}}, {"_id": {"order": "asc"}}]


@dataclass(slots=True)
class PagedHits:
    hits: list[dict[str, Any]]
    total_hits: int
    page_count: int


EVIDENCE_KEYWORDS = ("conversation", "task", "error", "warn")


def fetch_all_hits(
    *,
    client: Any,
    query: str,
    index: str,
    start_time: str | None,
    end_time: str | None,
    page_size: int,
    max_pages: int,
) -> PagedHits:
    total_hits = client.count(
        query=query,
        index=index,
        start_time=start_time,
        end_time=end_time,
    )

    all_hits: list[dict[str, Any]] = []
    cursor: list[Any] | None = None
    page_count = 0

    while page_count < max_pages:
        response = client.search(
            query=query,
            index=index,
            start_time=start_time,
            end_time=end_time,
            size=page_size,
            sort=DISCOVERY_SORT,
            search_after=cursor,
        )
        hits = response.get("hits", {}).get("hits", [])
        if not hits:
            break

        all_hits.extend(hits)
        page_count += 1

        if len(hits) < page_size:
            break

        cursor = hits[-1].get("sort")
        if not cursor:
            break

    return PagedHits(hits=all_hits, total_hits=total_hits, page_count=page_count)


def aggregate_sessions(
    *,
    hits: list[dict[str, Any]],
    session_key: str,
    matched_field_name: str | None,
) -> list[DiscoverySession]:
    sessions: dict[str, DiscoverySession] = {}
    session_logs: dict[str, list[dict[str, Any]]] = {}

    for hit in hits:
        source = hit.get("_source", {})
        session_id = source.get(session_key)
        if not session_id:
            continue

        timestamp = source.get("@timestamp", "")
        session = sessions.get(session_id)
        if session is None:
            session = DiscoverySession(
                session_id=session_id,
                first_timestamp=timestamp,
                last_timestamp=timestamp,
                log_count=0,
            )
            sessions[session_id] = session
            session_logs[session_id] = []

        session.log_count += 1
        session.first_timestamp = min(session.first_timestamp, timestamp)
        session.last_timestamp = max(session.last_timestamp, timestamp)
        session.conversation_id = session.conversation_id or source.get("conversationId")
        session.task_id = session.task_id or source.get("taskId")
        session.extension_id = session.extension_id or source.get("extensionId")
        if matched_field_name and matched_field_name in source:
            session.matched_fields[matched_field_name] = source[matched_field_name]

        session_logs[session_id].append(source)

    for session_id, session in sessions.items():
        session.evidence = select_evidence_lines(session_logs[session_id])

    return sorted(sessions.values(), key=lambda session: session.first_timestamp)


def select_evidence_lines(logs: list[dict[str, Any]], limit: int = 4) -> list[str]:
    scored_messages: list[tuple[int, int, str]] = []

    for index, source in enumerate(logs):
        message = source.get("message")
        if not message:
            continue
        score = _score_message(message)
        if index == 0:
            score += 1
        scored_messages.append((score, -index, message))

    scored_messages.sort(reverse=True)

    selected: list[str] = []
    for score, _, message in scored_messages:
        if score <= 0:
            continue
        if message not in selected:
            selected.append(message)
        if len(selected) >= limit:
            break

    return selected


def _score_message(message: str) -> int:
    lowered = message.lower()
    score = sum(2 for keyword in EVIDENCE_KEYWORDS if keyword in lowered)
    if lowered.startswith("start") or "start processing" in lowered:
        score += 1
    return score
