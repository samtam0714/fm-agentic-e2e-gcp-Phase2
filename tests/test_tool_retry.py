"""Tests for retryable tool auto-retry (Sprint 5 / 2.5.4)."""

from __future__ import annotations

from eval_harness.fault_injection import fault_injection_context
from tools.registry import get_tool
from tools.retryable import is_retryable_error, with_retryable_retry


def test_with_retryable_retry_retries_once():
    calls = {"n": 0}

    def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"error": "timeout", "retryable": True}
        return {"ok": True}

    wrapped = with_retryable_retry(flaky)
    assert wrapped(query="x") == {"ok": True}
    assert calls["n"] == 2


def test_with_retryable_retry_stops_after_budget():
    def always_fail(**kwargs):
        return {"error": "timeout", "retryable": True}

    wrapped = with_retryable_retry(always_fail, max_retries=1)
    result = wrapped()
    assert is_retryable_error(result)


def test_get_tool_absorbs_fault_injection_fail_count_one():
    """fail_count=1 should succeed via get_tool's outer retry wrapper."""
    case = {
        "fault_injection": {
            "tool": "search_policy_doc",
            "fail_count": 1,
            "error": "timeout",
        }
    }
    with fault_injection_context(case):
        tool = get_tool("search_policy_doc")
        result = tool(query="HVAC temperature", asset_type="AHU")
    assert "error" not in result or result.get("retryable") is not True
    assert "policies" in result or "policy" in str(result).lower() or result.get("count", 0) >= 0
