"""Tests for recovery gate replan / escalate behavior."""

from __future__ import annotations

from types import SimpleNamespace

from agents.root_agent.recovery import (
    find_latest_retryable_tool_error,
)


def test_find_latest_retryable_tool_error():
    fn = SimpleNamespace(
        name="search_policy_doc",
        response={"error": "timeout", "retryable": True, "message": "boom"},
    )
    part = SimpleNamespace(function_response=fn, text=None, function_call=None)
    event = SimpleNamespace(content=SimpleNamespace(parts=[part]))
    ctx = SimpleNamespace(session=SimpleNamespace(events=[event]))

    err = find_latest_retryable_tool_error(ctx)
    assert err is not None
    assert err["tool"] == "search_policy_doc"
    assert err["retryable"] is True


def test_find_latest_retryable_tool_error_none_when_clean():
    fn = SimpleNamespace(name="search_policy_doc", response={"policies": []})
    part = SimpleNamespace(function_response=fn, text=None, function_call=None)
    event = SimpleNamespace(content=SimpleNamespace(parts=[part]))
    ctx = SimpleNamespace(session=SimpleNamespace(events=[event]))
    assert find_latest_retryable_tool_error(ctx) is None
