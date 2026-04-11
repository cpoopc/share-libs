from __future__ import annotations

from pathlib import Path
from typing import Any
import json


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"tickets": {}}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
