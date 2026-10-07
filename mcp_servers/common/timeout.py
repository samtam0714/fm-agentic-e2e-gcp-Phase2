"""Shared timeout helper for MCP tool servers (Sprint 3 contract: timeout -> retryable)."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, TypeVar

T = TypeVar("T")

DEFAULT_TIMEOUT_SECONDS = 30.0


def tool_timeout_seconds() -> float:
    raw = os.getenv("MCP_TOOL_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        return max(0.01, float(raw))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def force_timeout_enabled() -> bool:
    return os.getenv("MCP_FORCE_TIMEOUT", "").strip().lower() in {"1", "true", "yes"}


def simulate_slow_seconds() -> float:
    raw = os.getenv("MCP_SIMULATE_SLOW_SECONDS", "").strip()
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


def timeout_error_payload(*, timeout_seconds: float, tool: str) -> dict[str, Any]:
    """Structured, retryable error - matches eval fault_injection shape."""
    return {
        "error": "timeout",
        "retryable": True,
        "tool": tool,
        "message": f"Tool '{tool}' exceeded timeout of {timeout_seconds:.3f}s",
        "timeout_seconds": timeout_seconds,
    }


def run_with_timeout(
    fn: Callable[..., T],
    /,
    *args: Any,
    tool_name: str,
    timeout_seconds: float | None = None,
    **kwargs: Any,
) -> T | dict[str, Any]:
    """Run a sync tool under a wall-clock timeout.

    On timeout (or MCP_FORCE_TIMEOUT), returns a structured retryable error dict
    instead of raising - so MCP CallTool stays isError=False with JSON body the
    agent can inspect and retry.
    """
    limit = tool_timeout_seconds() if timeout_seconds is None else max(0.01, timeout_seconds)

    if force_timeout_enabled():
        return timeout_error_payload(timeout_seconds=limit, tool=tool_name)

    slow = simulate_slow_seconds()
    if slow > 0:
        # Contract-test hook: sleep before/around the real call budget.
        def _wrapped() -> T:
            time.sleep(slow)
            return fn(*args, **kwargs)

        target: Callable[[], T] = _wrapped
    else:

        def target() -> T:
            return fn(*args, **kwargs)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(target)
        try:
            return future.result(timeout=limit)
        except FuturesTimeoutError:
            future.cancel()
            return timeout_error_payload(timeout_seconds=limit, tool=tool_name)
