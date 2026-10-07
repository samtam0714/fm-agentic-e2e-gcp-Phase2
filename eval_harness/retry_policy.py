"""Rate-limit and network retry policy shared by agent and LLM judge calls."""

from __future__ import annotations

import os
import random
import time

CASE_DELAY_SECONDS = int(os.environ.get("EVAL_CASE_DELAY_SECONDS", "60"))
CASE_MAX_RETRIES = int(os.environ.get("EVAL_CASE_MAX_RETRIES", "12"))
CASE_RETRY_MAX_WAIT = int(os.environ.get("EVAL_CASE_RETRY_MAX_WAIT", "600"))
RATE_LIMIT_COOLDOWN = int(os.environ.get("EVAL_RATE_LIMIT_COOLDOWN", "180"))

_last_rate_limit_monotonic: float | None = None
_rate_limit_event_count = 0


def note_rate_limit() -> None:
    """Record the latest 429 so later cases can apply an extra cooldown."""
    global _last_rate_limit_monotonic, _rate_limit_event_count
    _last_rate_limit_monotonic = time.monotonic()
    _rate_limit_event_count += 1


def seconds_until_quota_cooldown() -> float:
    """Return seconds remaining in quota cooldown, or zero if ready."""
    if _last_rate_limit_monotonic is None:
        return 0.0
    elapsed = time.monotonic() - _last_rate_limit_monotonic
    return max(0.0, RATE_LIMIT_COOLDOWN - elapsed)


def _walk_exceptions(exc: BaseException):
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def is_rate_limit_error(exc: BaseException) -> bool:
    """Return whether an error is Vertex 429/RESOURCE_EXHAUSTED, including ADK wrappers."""
    for current in _walk_exceptions(exc):
        message = str(current).lower()
        name = type(current).__name__.lower()
        if "429" in message or "resource_exhausted" in message or "resourceexhausted" in name:
            return True
        try:
            from google.genai.errors import ClientError

            if isinstance(current, ClientError) and getattr(current, "code", None) == 429:
                return True
        except ImportError:
            pass
    return False


# Transient Vertex/GCP server codes: unavailable, internal, timeout, and gateway errors
_TRANSIENT_SERVER_CODES = {500, 502, 503, 504}
_TRANSIENT_SERVER_STATUSES = (
    "unavailable",
    "internal",
    "deadline_exceeded",
    "aborted",
    "authentication backend unavailable",
)


def is_transient_server_error(exc: BaseException) -> bool:
    """Return whether this is a transient Vertex 5xx server error.

    These are usually temporary backend failures that recover after a retry.
    """
    for current in _walk_exceptions(exc):
        message = str(current).lower()
        name = type(current).__name__.lower()
        if "servererror" in name:
            return True
        code = getattr(current, "code", None)
        if code in _TRANSIENT_SERVER_CODES:
            return True
        if any(str(c) in message for c in _TRANSIENT_SERVER_CODES) and (
            "unavailable" in message or "internal" in message or "backend" in message
        ):
            return True
        if any(status in message for status in _TRANSIENT_SERVER_STATUSES):
            return True
    return False


def is_retryable_eval_error(exc: BaseException) -> bool:
    """Return whether a rate-limit, server, or network error is retryable."""
    if is_rate_limit_error(exc):
        return True
    if is_transient_server_error(exc):
        return True
    for current in _walk_exceptions(exc):
        message = str(current).lower()
        name = type(current).__name__.lower()
        if "readerror" in message or "connecterror" in message or "timeout" in message:
            return True
        if name in {"readerror", "connecterror", "connecttimeout", "readtimeout"}:
            return True
    return False


def retry_wait_seconds(attempt: int, *, rate_limited: bool) -> float:
    """Use capped exponential backoff for limits and linear backoff for network errors."""
    if rate_limited:
        wait = min(CASE_RETRY_MAX_WAIT, CASE_DELAY_SECONDS * (2 ** (attempt - 1)))
    else:
        wait = CASE_DELAY_SECONDS * attempt
    return wait + random.uniform(0, 10)


def inter_case_delay_seconds() -> float:
    """Compute inter-case delay, increasing exponentially after observed 429s."""
    if _rate_limit_event_count == 0:
        return CASE_DELAY_SECONDS + random.uniform(0, 10)
    multiplier = min(4, 2 ** min(_rate_limit_event_count, 3))
    return CASE_DELAY_SECONDS * multiplier + random.uniform(0, 15)


def pre_judge_delay_seconds() -> float:
    """Compute extra cooldown between an agent run and the LLM judge."""
    cooldown = seconds_until_quota_cooldown()
    if cooldown > 0:
        return cooldown
    if _rate_limit_event_count > 0:
        return CASE_DELAY_SECONDS * 0.5 + random.uniform(0, 10)
    return CASE_DELAY_SECONDS * 0.25 + random.uniform(0, 5)


def format_rate_limit_hint(case_id: str | None = None) -> str:
    """Return an operator-facing explanation of automatic Vertex retries."""
    label = f"case {case_id}" if case_id else "current request"
    return (
        f"[eval] Vertex rate limit (429), {label}; waiting before automatic retry "
        f"(configure EVAL_CASE_DELAY_SECONDS / EVAL_CASE_MAX_RETRIES)"
    )
