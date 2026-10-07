"""Remote WorkOrder A2A HTTP server (Sprint 7 / 2.7.1).

Run:
  uv run workorder-a2a
  # or: uvicorn agents.workorder_agent.a2a_server:app --port 8091
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from agents.workorder_agent.a2a_protocol import (
    AGENT_CARD_PATH,
    TRACE_HEADER,
    A2AMessageSendRequest,
    A2AMessageSendResponse,
    A2AArtifact,
    A2ATask,
    A2ATaskStatus,
    A2ATextPart,
    parse_recommendation_payload,
    recommendation_text_from_tool,
)
from agents.workorder_agent.tools import recommend_work_order
from observability.logging.structured_logger import get_logger
from observability.tracing.models import TraceSpan
from observability.tracing.span_recorder import SpanRecorder
from observability.tracing.trace_context import TraceContext, set_trace_context
from tools.registry import get_tool

_log = get_logger(__name__)

load_dotenv()

AGENT_CARD_FILE = (
    Path(__file__).resolve().parents[2] / "deployment" / "a2a" / "agent_card.json"
)

app = FastAPI(
    title="FM AgentOps WorkOrder A2A",
    description="Mini A2A remote WorkOrder agent for Phase 2 Sprint 7.",
    version="1.0.0",
)


def _load_agent_card() -> dict:
    with open(AGENT_CARD_FILE, encoding="utf-8") as f:
        card = json.load(f)
    base = os.getenv("WORKORDER_A2A_PUBLIC_URL", card.get("url", "http://127.0.0.1:8091/"))
    card["url"] = base if base.endswith("/") else base + "/"
    if card.get("additionalInterfaces"):
        card["additionalInterfaces"][0]["url"] = (
            card["url"].rstrip("/") + "/a2a/v1/message:send"
        )
    return card


def _apply_fault_injection() -> None:
    """Test hooks: WORKORDER_A2A_FAULT=timeout|unavailable|invalid."""
    fault = os.getenv("WORKORDER_A2A_FAULT", "").strip().lower()
    if fault == "timeout":
        delay = float(os.getenv("WORKORDER_A2A_TIMEOUT_SLEEP", "5"))
        time.sleep(delay)
        raise HTTPException(status_code=504, detail="injected timeout")
    if fault == "unavailable":
        raise HTTPException(status_code=503, detail="injected unavailable")
    if fault == "invalid":
        # Handled in endpoint by returning a non-schema body.
        return


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "workorder-a2a"}


@app.get(AGENT_CARD_PATH)
@app.get("/.well-known/agent-card.json")
async def agent_card() -> JSONResponse:
    return JSONResponse(_load_agent_card())


@app.post("/a2a/v1/message:send")
async def message_send(
    request: Request,
    x_trace_id: str | None = Header(default=None, alias=TRACE_HEADER),
) -> JSONResponse:
    fault = os.getenv("WORKORDER_A2A_FAULT", "").strip().lower()
    if fault == "invalid":
        # Intentionally break the contract for client invalid-response tests.
        return JSONResponse({"not": "a-valid-a2a-response"}, status_code=200)

    _apply_fault_injection()

    body = await request.json()
    try:
        payload = A2AMessageSendRequest.model_validate(body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid request: {exc}") from exc

    trace_id = (
        x_trace_id
        or str(payload.message.metadata.get("trace_id") or "")
        or f"tr_{uuid.uuid4().hex[:12]}"
    )
    set_trace_context(TraceContext(trace_id=trace_id, app_name="workorder-a2a"))
    started = time.perf_counter()

    text = " ".join(p.text for p in payload.message.parts if p.type == "text")
    kwargs = parse_recommendation_payload(text, payload.message.metadata)
    if not kwargs.get("asset_id"):
        raise HTTPException(status_code=400, detail="asset_id is required")

    # Use registry wrapper so retryable middleware stays consistent with in-process.
    tool = get_tool("recommend_work_order")
    result = tool(**{k: v for k, v in kwargs.items() if v is not None})
    # Fall back to bare tool if registry wraps unexpectedly in tests
    if not isinstance(result, dict):
        result = recommend_work_order(**{k: v for k, v in kwargs.items() if v is not None})

    recommendation = recommendation_text_from_tool(result)
    latency_ms = (time.perf_counter() - started) * 1000
    # Same trace_id as Root -> spans can be joined in JSONL / Cloud Trace / BQ.
    try:
        SpanRecorder(trace_id).append_span(
            TraceSpan(
                trace_id=trace_id,
                agent="workorder-a2a",
                step="a2a.message_send",
                input_summary=text[:200],
                output_summary=recommendation[:200],
                latency_ms=latency_ms,
                tool_calls=["recommend_work_order"],
                span_type="agent_turn",
                status="success",
            )
        )
    except OSError:
        pass
    _log.info(
        "a2a.message_send",
        asset_id=kwargs.get("asset_id"),
        latency_ms=round(latency_ms, 2),
    )

    task = A2ATask(
        id=f"task_{uuid.uuid4().hex[:10]}",
        status=A2ATaskStatus(state="completed"),
        artifacts=[A2AArtifact(parts=[A2ATextPart(text=recommendation)])],
        metadata={
            "service": "workorder-a2a",
            "asset_id": kwargs.get("asset_id"),
            "tool_result": result,
        },
    )
    response = A2AMessageSendResponse(task=task, trace_id=trace_id)
    return JSONResponse(
        response.model_dump(),
        headers={TRACE_HEADER: trace_id},
    )


def main() -> None:
    import uvicorn

    host = os.getenv("WORKORDER_A2A_HOST", "0.0.0.0")
    port = int(os.getenv("WORKORDER_A2A_PORT", "8091"))
    uvicorn.run(
        "agents.workorder_agent.a2a_server:app",
        host=host,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
