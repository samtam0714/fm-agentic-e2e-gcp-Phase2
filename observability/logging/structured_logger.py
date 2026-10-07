"""Structured JSON logging with request-scoped trace_id (Sprint 4 / 2.4.3).

Each log record carries the same trace_id so agent, tool, and evaluation events
from one request can be correlated later.

Usage:
    from observability.logging import get_logger
    log = get_logger(__name__)
    log.info("investigation.started", query=query[:80])
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from observability.tracing.trace_context import get_trace_context


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line (Cloud Logging / jq friendly)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        ctx = get_trace_context()
        if ctx is not None:
            payload["trace_id"] = ctx.trace_id
            if ctx.session_id:
                payload["session_id"] = ctx.session_id
            if ctx.app_name:
                payload["app_name"] = ctx.app_name

        # Extra fields passed via StructuredLogger.log(..., key=value)
        extras = getattr(record, "structured_fields", None)
        if isinstance(extras, dict):
            for key, value in extras.items():
                if key not in payload:
                    payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


class StructuredLogger:
    """Thin wrapper: always attach ContextVar trace fields to JSON logs."""

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def _log(
        self,
        level: int,
        message: str,
        *,
        exc_info: bool = False,
        **fields: Any,
    ) -> None:
        extra = {"structured_fields": fields} if fields else {}
        self._logger.log(level, message, extra=extra, exc_info=exc_info)

    def debug(self, message: str, **fields: Any) -> None:
        self._log(logging.DEBUG, message, **fields)

    def info(self, message: str, **fields: Any) -> None:
        self._log(logging.INFO, message, **fields)

    def warning(self, message: str, **fields: Any) -> None:
        self._log(logging.WARNING, message, **fields)

    def error(self, message: str, **fields: Any) -> None:
        # Allow log.error("...", exc_info=True) like stdlib logging
        exc_info = bool(fields.pop("exc_info", False))
        self._log(logging.ERROR, message, exc_info=exc_info, **fields)


_CONFIGURED = False


def configure_structured_logging(*, level: int = logging.INFO) -> None:
    """Install JSON formatter on the root logger once (idempotent)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    _CONFIGURED = True


def get_logger(name: str) -> StructuredLogger:
    """Return a structured logger; configures JSON output on first use."""
    configure_structured_logging()
    return StructuredLogger(name)
