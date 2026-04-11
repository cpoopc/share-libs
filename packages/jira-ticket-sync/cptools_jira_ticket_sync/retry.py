from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar
import time


T = TypeVar("T")


def run_with_backoff(
    fn: Callable[[], T],
    *,
    is_retryable: Callable[[T], bool],
    max_attempts: int = 3,
    sleep_seconds: float = 0.01,
) -> T:
    attempt = 0
    last_result: T | None = None
    while attempt < max_attempts:
        last_result = fn()
        if not is_retryable(last_result):
            return last_result
        attempt += 1
        if attempt < max_attempts:
            time.sleep(sleep_seconds)
    return last_result  # type: ignore[return-value]

