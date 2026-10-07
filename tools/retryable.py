"""Transparent one-shot retry for retryable tool errors (Sprint 5 / 2.5.4)."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any

ToolFn = Callable[..., dict[str, Any]]


def is_retryable_error(result: Any) -> bool:
    return isinstance(result, dict) and result.get("retryable") is True


def with_retryable_retry(func: ToolFn, *, max_retries: int = 1) -> ToolFn:
    """Wrap a tool so a retryable error dict triggers up to max_retries extra calls.

    Intended to sit *outside* fault_injection wrappers so fail_count=1 is absorbed
    before the agent sees the error.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        attempts = 0
        while True:
            result = func(*args, **kwargs)
            attempts += 1
            if is_retryable_error(result) and attempts <= max_retries:
                continue
            return result if isinstance(result, dict) else {"raw": result}

    try:
        wrapper.__signature__ = inspect.signature(func)  # type: ignore[attr-defined]
    except (TypeError, ValueError):
        pass
    return wrapper
