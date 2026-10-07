"""Request and response models for the investigate API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InvestigateRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language investigation request")
    user_id: str | None = Field(default=None, description="Optional caller user id")


class WorkOrderRecommendation(BaseModel):
    action: str | None = None
    priority: str | None = None
    fm_priority: str | None = None
    should_create: bool | None = None
    should_update: bool | None = None
    summary: str | None = None
    rationale: str | None = None


class AuditorVerdict(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    grounded: bool | None = None
    passed: bool | None = Field(default=None, alias="pass", serialization_alias="pass")
    summary: str | None = None
    violations: list[str] = Field(default_factory=list)
    must_not_violations: list[str] = Field(default_factory=list)


class InvestigateResponse(BaseModel):
    trace_id: str
    session_id: str
    latency_seconds: float
    query: str
    alarm_summary: str | None = None
    policy_context: str | None = None
    work_order_text: str | None = None
    auditor_text: str | None = None
    work_order_recommendation: WorkOrderRecommendation | None = None
    auditor_verdict: AuditorVerdict | None = None
    similar_cases: list[dict[str, Any]] = Field(default_factory=list)
    tools_called: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "fm-agentops"
