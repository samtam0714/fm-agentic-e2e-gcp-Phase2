"""Mini A2A message shapes for the remote WorkOrder agent (Sprint 7).

Compatible with A2A agent-card discovery; uses a simplified HTTP+JSON
message:send contract that is easy to test without the full a2a-sdk /
RemoteA2aAgent version pin (ADK 2.2.0 expects APIs not in a2a-sdk 1.1.2).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

TRACE_HEADER = "X-Trace-Id"
DEFAULT_A2A_BASE_URL = "http://127.0.0.1:8091"
AGENT_CARD_PATH = "/.well-known/agent.json"
MESSAGE_SEND_PATH = "/a2a/v1/message:send"

_ASSET_RE = re.compile(r"\b(?:AHU|VAV|RTU|FCU)-[\w-]+\b", re.IGNORECASE)


class A2ATextPart(BaseModel):
    type: str = "text"
    text: str = ""


class A2AMessage(BaseModel):
    role: str = "user"
    parts: list[A2ATextPart] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class A2AMessageSendRequest(BaseModel):
    message: A2AMessage
    configuration: dict[str, Any] = Field(default_factory=dict)


class A2ATaskStatus(BaseModel):
    state: str = "completed"
    message: str | None = None


class A2AArtifact(BaseModel):
    parts: list[A2ATextPart] = Field(default_factory=list)


class A2ATask(BaseModel):
    id: str
    status: A2ATaskStatus = Field(default_factory=A2ATaskStatus)
    artifacts: list[A2AArtifact] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class A2AMessageSendResponse(BaseModel):
    task: A2ATask
    trace_id: str = ""


class A2AClientError(Exception):
    """Structured remote WorkOrder failure."""

    def __init__(
        self,
        *,
        error: str,
        retryable: bool = False,
        message: str = "",
        status_code: int | None = None,
    ) -> None:
        self.error = error
        self.retryable = retryable
        self.message = message
        self.status_code = status_code
        super().__init__(message or error)


def extract_asset_id(*texts: str | None) -> str | None:
    for text in texts:
        if not text:
            continue
        match = _ASSET_RE.search(str(text))
        if match:
            return match.group(0).upper()
    return None


def recommendation_text_from_tool(result: dict[str, Any]) -> str:
    """Format recommend_work_order output for agent state / A2A artifact."""
    if result.get("error"):
        return (
            f"Work order tool error: {result.get('error')}. "
            "Recommend monitoring / no_action."
        )
    rec = result.get("recommendation") or {}
    action = rec.get("action", "no_action")
    priority = rec.get("priority", "low")
    wo_id = rec.get("work_order_id") or "none"
    rationale = rec.get("rationale") or rec.get("reason") or ""
    return (
        f"action={action}; priority={priority}; work_order_id={wo_id}; "
        f"rationale={rationale}"
    )


def parse_recommendation_payload(
    text: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build recommend_work_order kwargs from A2A message text + metadata."""
    meta = metadata or {}
    asset_id = (
        str(meta.get("asset_id") or "").strip()
        or extract_asset_id(text, str(meta.get("alarm_summary") or ""))
        or ""
    )
    event_count = int(meta.get("event_count") or 0)
    is_recurring = bool(meta.get("is_recurring"))
    if not is_recurring and "recurring" in (text or "").lower():
        is_recurring = True
    alarm_priority = meta.get("alarm_priority")
    policy_ids = meta.get("policy_ids")
    if isinstance(policy_ids, str):
        policy_ids = [policy_ids]
    likely_cause = meta.get("likely_cause")
    return {
        "asset_id": asset_id,
        "event_count": event_count,
        "is_recurring": is_recurring,
        "alarm_priority": alarm_priority,
        "policy_ids": policy_ids,
        "likely_cause": likely_cause,
    }
