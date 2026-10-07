"""Unit tests for structured JSON logging (Sprint 4 / 2.4.3)."""

from __future__ import annotations

import json
import logging

from observability.logging.structured_logger import (
    JsonFormatter,
    StructuredLogger,
    get_logger,
)
from observability.tracing import TraceContext
from observability.tracing.trace_context import clear_trace_context, set_trace_context


def test_json_formatter_includes_trace_id():
    set_trace_context(TraceContext(trace_id="tr_test123", session_id="sess_1"))
    try:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        record.structured_fields = {"event": "demo"}
        line = JsonFormatter().format(record)
        payload = json.loads(line)
        assert payload["message"] == "hello"
        assert payload["trace_id"] == "tr_test123"
        assert payload["session_id"] == "sess_1"
        assert payload["event"] == "demo"
        assert payload["level"] == "INFO"
    finally:
        clear_trace_context()


def test_json_formatter_works_without_context():
    clear_trace_context()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="no-ctx",
        args=(),
        exc_info=None,
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "no-ctx"
    assert "trace_id" not in payload


def test_get_logger_returns_structured_logger():
    log = get_logger("observability.test")
    assert isinstance(log, StructuredLogger)
