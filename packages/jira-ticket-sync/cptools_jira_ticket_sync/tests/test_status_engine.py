from __future__ import annotations

import pytest

from cptools_jira_ticket_sync.status_engine import compute_status, compute_field_hash


@pytest.mark.parametrize(
    ("local_hash", "remote_hash", "last_hash", "expected"),
    [
        (None, None, None, "draft"),
        ("a", "a", "a", "in_sync"),
        ("b", "a", "a", "local_changed"),
        ("a", "b", "a", "remote_changed"),
        ("b", "c", "a", "conflict"),
    ],
)
def test_compute_status(local_hash: str | None, remote_hash: str | None, last_hash: str | None, expected: str) -> None:
    assert compute_status(local_hash, remote_hash, last_hash) == expected


def test_compute_field_hash_is_stable_for_same_payload() -> None:
    payload = {"summary": "hello", "priority": "Medium", "labels": ["a", "b"]}
    assert compute_field_hash(payload) == compute_field_hash(payload)
