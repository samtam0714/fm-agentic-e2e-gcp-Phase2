"""Investigate endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from api.schemas import (
    AuditorVerdict,
    InvestigateRequest,
    InvestigateResponse,
    WorkOrderRecommendation,
)
from services.investigate import InvestigationResult, run_investigation

router = APIRouter(prefix="/v1", tags=["investigate"])


def _build_work_order_recommendation(tool_results: dict) -> WorkOrderRecommendation | None:
    payload = tool_results.get("recommend_work_order")
    if not isinstance(payload, dict):
        return None
    recommendation = payload.get("recommendation")
    if not isinstance(recommendation, dict):
        return None
    return WorkOrderRecommendation(
        action=recommendation.get("action"),
        priority=recommendation.get("priority"),
        fm_priority=recommendation.get("fm_priority"),
        should_create=recommendation.get("should_create"),
        should_update=recommendation.get("should_update"),
        summary=recommendation.get("summary"),
        rationale=recommendation.get("rationale"),
    )


def _build_auditor_verdict(tool_results: dict) -> AuditorVerdict | None:
    payload = tool_results.get("audit_recommendation")
    if not isinstance(payload, dict):
        return None
    return AuditorVerdict(
        grounded=payload.get("grounded"),
        passed=payload.get("pass"),
        summary=payload.get("summary"),
        violations=payload.get("violations") or [],
        must_not_violations=payload.get("must_not_violations") or [],
    )


def build_investigate_response(result: InvestigationResult) -> InvestigateResponse:
    """Map investigation pipeline output to API response schema."""
    snapshot = result.session_snapshot
    return InvestigateResponse(
        trace_id=result.trace_id,
        session_id=result.session_id,
        latency_seconds=round(result.latency_seconds, 3),
        query=result.query,
        alarm_summary=snapshot.get("alarm_summary"),
        policy_context=snapshot.get("policy_context"),
        work_order_text=snapshot.get("work_order_recommendation"),
        auditor_text=snapshot.get("auditor_verdict"),
        work_order_recommendation=_build_work_order_recommendation(result.tool_results),
        auditor_verdict=_build_auditor_verdict(result.tool_results),
        similar_cases=snapshot.get("similar_cases") or [],
        tools_called=result.tools,
        agents=result.agents,
    )


@router.post("/investigate", response_model=InvestigateResponse)
async def investigate(request: Request, body: InvestigateRequest) -> InvestigateResponse:
    """Run the multi-agent investigate pipeline for a building alarm query."""
    trace_id = getattr(request.state, "trace_id", None)
    user_id = body.user_id or "api-user"

    result = await run_investigation(
        body.query,
        user_id=user_id,
        trace_id=trace_id,
    )
    return build_investigate_response(result)
