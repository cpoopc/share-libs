from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class DiscoveryRequest:
    env: str
    index: str
    field: str | None
    value: str | None
    query: str | None
    session_key: str
    page_size: int
    max_pages: int
    start_time: str | None
    end_time: str | None

    def to_dict(self) -> dict[str, Any]:
        query_mode = "query_string" if self.query else "field_value"
        time_range: dict[str, Any] = {
            "last": None,
            "start": None,
            "end": None,
        }
        if self.start_time and self.start_time.startswith("now-") and self.end_time == "now":
            time_range["last"] = self.start_time.removeprefix("now-")
        else:
            time_range["start"] = self.start_time
            time_range["end"] = self.end_time

        return {
            "env": self.env,
            "index": self.index,
            "query_mode": query_mode,
            "field": self.field,
            "value": self.value,
            "query": self.query,
            "session_key": self.session_key,
            "page_size": self.page_size,
            "max_pages": self.max_pages,
            "time_range": time_range,
        }


@dataclass(slots=True)
class DiscoveryStats:
    total_hits: int
    fetched_hits: int
    page_size: int
    page_count: int
    session_count: int
    complete: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DiscoverySession:
    session_id: str
    first_timestamp: str
    last_timestamp: str
    log_count: int
    conversation_id: str | None = None
    task_id: str | None = None
    extension_id: str | int | None = None
    matched_fields: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "sessionId": self.session_id,
            "firstTimestamp": self.first_timestamp,
            "lastTimestamp": self.last_timestamp,
            "logCount": self.log_count,
            "conversationId": self.conversation_id,
            "taskId": self.task_id,
            "extensionId": self.extension_id,
            "matchedFields": self.matched_fields,
            "evidence": self.evidence,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(slots=True)
class DiscoveryResult:
    query: DiscoveryRequest
    stats: DiscoveryStats
    sessions: list[DiscoverySession]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query.to_dict(),
            "stats": self.stats.to_dict(),
            "sessions": [session.to_dict() for session in self.sessions],
        }
