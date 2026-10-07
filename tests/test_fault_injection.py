import inspect

from eval_harness.fault_injection import fault_injection_context, wrap_tool


def _ok_tool(query: str, asset_type: str | None = None) -> dict:
    return {"ok": True, "query": query, "asset_type": asset_type}


def test_wrap_tool_fails_then_succeeds():
    wrapped = wrap_tool("search_policy_doc", _ok_tool)
    case = {
        "fault_injection": {
            "tool": "search_policy_doc",
            "fail_count": 1,
            "error": "timeout",
        }
    }

    with fault_injection_context(case):
        first = wrapped(query="hvac")
        second = wrapped(query="hvac")

    assert first["error"] == "timeout"
    assert first["retryable"] is True
    assert second["ok"] is True
    assert second["query"] == "hvac"


def test_wrap_tool_replays_args_when_retry_is_empty():
    """Replay prior arguments when a Gemini/ADK retry omits query."""
    wrapped = wrap_tool("search_policy_doc", _ok_tool)
    case = {
        "fault_injection": {
            "tool": "search_policy_doc",
            "fail_count": 1,
            "error": "timeout",
        }
    }

    with fault_injection_context(case):
        first = wrapped(query="hvac", asset_type="AHU")
        second = wrapped()  # Simulate an ADK retry with empty kwargs.

    assert first["error"] == "timeout"
    assert second["ok"] is True
    assert second["query"] == "hvac"
    assert second["asset_type"] == "AHU"


def test_wrap_tool_preserves_function_signature():
    wrapped = wrap_tool("search_policy_doc", _ok_tool)
    assert wrapped.__name__ == "_ok_tool"
    params = list(inspect.signature(wrapped).parameters)
    assert params == ["query", "asset_type"]


def test_fault_injection_noop_without_config():
    wrapped = wrap_tool("search_policy_doc", _ok_tool)
    with fault_injection_context(None):
        result = wrapped(query="hvac")
    assert result["ok"] is True
