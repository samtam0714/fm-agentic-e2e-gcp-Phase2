"""Evaluation runner retry tests."""

import httpx
from google.genai.errors import ClientError

from google.genai.errors import ServerError

from eval_harness.retry_policy import (
    is_rate_limit_error,
    is_retryable_eval_error,
    is_transient_server_error,
    retry_wait_seconds,
)


def test_retryable_on_rate_limit():
    assert is_retryable_eval_error(Exception("429 RESOURCE_EXHAUSTED")) is True


def test_rate_limit_on_adk_wrapped_error():
    """ADK _ResourceExhaustedError often stores the 429 in __cause__."""
    inner = ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}}, None)

    class _ResourceExhaustedError(Exception):
        pass

    outer = _ResourceExhaustedError("quota")
    outer.__cause__ = inner
    assert is_rate_limit_error(outer) is True
    assert is_retryable_eval_error(outer) is True


def test_retryable_on_read_error():
    assert is_retryable_eval_error(httpx.ReadError("connection dropped")) is True


def test_retryable_on_503_server_error():
    """Vertex 503 UNAVAILABLE is retried without aborting the evaluation run."""
    exc = ServerError(
        503,
        {"error": {"code": 503, "message": "Authentication backend unavailable.", "status": "UNAVAILABLE"}},
        None,
    )
    assert is_transient_server_error(exc) is True
    assert is_retryable_eval_error(exc) is True
    assert is_rate_limit_error(exc) is False


def test_transient_server_error_via_message_chain():
    inner = ServerError(503, {"error": {"code": 503, "status": "UNAVAILABLE"}}, None)
    outer = RuntimeError("model call failed")
    outer.__cause__ = inner
    assert is_retryable_eval_error(outer) is True


def test_500_internal_is_retryable():
    exc = ServerError(500, {"error": {"code": 500, "status": "INTERNAL"}}, None)
    assert is_transient_server_error(exc) is True


def test_not_retryable_on_logic_error():
    assert is_retryable_eval_error(ValueError("bad input")) is False


def test_rate_limit_backoff_grows_faster_than_linear():
    limited = retry_wait_seconds(4, rate_limited=True)
    linear = retry_wait_seconds(4, rate_limited=False)
    assert limited > linear


def test_inter_case_delay_grows_after_rate_limits(monkeypatch):
    import eval_harness.retry_policy as policy

    monkeypatch.setattr(policy, "CASE_DELAY_SECONDS", 60)
    monkeypatch.setattr(policy, "_rate_limit_event_count", 0)
    baseline = policy.inter_case_delay_seconds()

    monkeypatch.setattr(policy, "_rate_limit_event_count", 2)
    after_limits = policy.inter_case_delay_seconds()
    assert after_limits > baseline


def test_pre_judge_delay_includes_cooldown(monkeypatch):
    import eval_harness.retry_policy as policy

    monkeypatch.setattr(policy, "seconds_until_quota_cooldown", lambda: 120.0)
    assert policy.pre_judge_delay_seconds() >= 120.0
