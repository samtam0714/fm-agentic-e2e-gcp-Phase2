"""Evaluation fault injection for testing recovery from tool timeout/failure.

Some golden cases configure fault_injection so a selected tool deliberately fails
its first few calls, testing whether the agent retries or degrades safely.

eval_harness/runner.py enables this automatically for evaluation only.
"""

from __future__ import annotations

import functools
import inspect
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable

# Fault configuration for the current golden case
_fault_config: ContextVar[dict[str, Any] | None] = ContextVar("fault_config", default=None)
# Number of injected failures per tool
_fault_call_counts: ContextVar[dict[str, int] | None] = ContextVar("fault_call_counts", default=None)
# Last arguments per tool, replayed when Gemini retries with empty kwargs
_last_invocation: ContextVar[dict[str, tuple[tuple[Any, ...], dict[str, Any]]] | None] = ContextVar(
    "last_invocation", default=None
)

# Tools eligible for fault injection; names match tools/registry.py
_PATCHABLE_TOOLS = (
    "search_alarm_history",
    "search_policy_doc",
    "recommend_work_order",
)


def _should_fail(tool_name: str) -> bool:
    """Return whether the current call should be deliberately failed."""
    config = _fault_config.get()
    if not config or config.get("tool") != tool_name:
        return False
    counts = _fault_call_counts.get()
    if counts is None:
        return False
    fail_count = int(config.get("fail_count", 1))
    counts[tool_name] = counts.get(tool_name, 0) + 1
    return counts[tool_name] <= fail_count


def _fault_response(config: dict[str, Any]) -> dict[str, Any]:
    """Build a synthetic tool failure response without raising an exception."""
    error = str(config.get("error", "timeout"))
    return {
        "error": error,
        "retryable": True,
        "message": f"Simulated {error} for eval fault injection",
    }


def _resolve_call_args(
    prev: tuple[tuple[Any, ...], dict[str, Any]] | None,
    func: Callable[..., dict[str, Any]],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Merge current and prior arguments when ADK omits fields during retries."""
    if prev is None:
        return args, kwargs

    prev_args, prev_kwargs = prev
    if not args and not kwargs:
        return prev_args, prev_kwargs

    if not args and prev_kwargs:
        merged_kwargs = {**prev_kwargs, **kwargs}
        try:
            inspect.signature(func).bind_partial(*args, **merged_kwargs)
            return args, merged_kwargs
        except TypeError:
            pass

    return args, kwargs


def wrap_tool(tool_name: str, func: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """Wrap a tool with its original signature and fail its first N calls."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        store = _last_invocation.get()
        prev = store.get(tool_name) if store is not None else None
        call_args, call_kwargs = _resolve_call_args(prev, func, args, kwargs)

        if store is not None and (call_args or call_kwargs):
            store[tool_name] = (call_args, call_kwargs)

        config = _fault_config.get()
        if config and _should_fail(tool_name):
            response = _fault_response(config)
            response["query"] = {"args": call_args, "kwargs": call_kwargs}
            return response

        return func(*call_args, **call_kwargs)

    return wrapper


@contextmanager
def fault_injection_context(case: dict[str, Any] | None):
    """Temporarily replace a registry tool for one case, then always restore it."""
    config = (case or {}).get("fault_injection")
    if not config:
        yield
        return

    import tools.registry as registry

    config_token = _fault_config.set(config)
    counts_token = _fault_call_counts.set({})
    invocation_token = _last_invocation.set({})
    originals: dict[str, Callable[..., dict[str, Any]]] = {}
    for name in _PATCHABLE_TOOLS:
        original = registry._REGISTRY[name]
        originals[name] = original
        registry._REGISTRY[name] = wrap_tool(name, original)
    try:
        yield
    finally:
        for name, original in originals.items():
            registry._REGISTRY[name] = original
        _last_invocation.reset(invocation_token)
        _fault_call_counts.reset(counts_token)
        _fault_config.reset(config_token)
