from __future__ import annotations

import hashlib
import json


def compute_status(local_hash: str | None, remote_hash: str | None, last_hash: str | None) -> str:
    if local_hash is None and remote_hash is None:
        return "draft"
    if local_hash == remote_hash:
        return "in_sync"
    if last_hash == remote_hash:
        return "local_changed"
    if last_hash == local_hash:
        return "remote_changed"
    return "conflict"


def compute_field_hash(payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
