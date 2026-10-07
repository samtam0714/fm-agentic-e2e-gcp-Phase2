"""API tests for FastAPI investigate gateway."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes.investigate import build_investigate_response
from services.investigate import InvestigationResult


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _sample_result() -> InvestigationResult:
    return InvestigationResult(
        query="Investigate Floor 3 HVAC alarm",
        trace_id="tr_api_test",
        session_id="sess_api_test",
        latency_seconds=12.345,
        agents=["alarm_agent", "kb_agent", "workorder_agent", "auditor_agent"],
        tools=[
            "search_alarm_history",
            "search_policy_doc",
            "recommend_work_order",
            "audit_recommendation",
        ],
        session_snapshot={
            "alarm_summary": "AHU-3F-01 recurring 7 events",
            "policy_context": "HVAC-MNT-003 applies",
            "work_order_recommendation": "Escalate WO-2026-0142 to high",
            "auditor_verdict": "grounded: yes pass: yes",
            "similar_cases": [{"case_id": "case_002", "asset_id": "AHU-3F-01"}],
        },
        tool_results={
            "recommend_work_order": {
                "recommendation": {
                    "action": "escalate_existing",
                    "priority": "high",
                    "fm_priority": "P1",
                    "should_create": False,
                    "should_update": True,
                    "summary": "Escalate existing work order",
                    "rationale": "Recurring P1 alarm with open WO",
                }
            },
            "audit_recommendation": {
                "grounded": True,
                "pass": True,
                "summary": "Audit passed",
                "violations": [],
                "must_not_violations": [],
            },
        },
        trace_path="/tmp/tr_api_test.jsonl",
        session_path="/tmp/sess_api_test.json",
    )


def test_health_endpoint(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "fm-agentops"}


def test_reliability_dashboard_endpoints(client: TestClient):
    """Sprint 4 dashboard HTML and metrics JSON endpoints are available."""
    html = client.get("/dashboard")
    assert html.status_code == 200
    assert "text/html" in html.headers.get("content-type", "")
    assert "FM AgentOps Reliability" in html.text

    metrics = client.get("/dashboard/metrics")
    assert metrics.status_code == 200
    body = metrics.json()
    assert "latency" in body
    assert "tool_error_rate" in body
    assert "judge_pass_rate" in body
    assert "release_gate" in body
    assert "top_failing_cases" in body
    assert "cost_estimate" in body
    assert "fallback_rate" in body
    assert "failure_recovery_rate" in body


def test_build_investigate_response_maps_structured_fields():
    response = build_investigate_response(_sample_result())
    assert response.trace_id == "tr_api_test"
    assert response.work_order_recommendation is not None
    assert response.work_order_recommendation.action == "escalate_existing"
    assert response.auditor_verdict is not None
    assert response.auditor_verdict.passed is True
    assert len(response.similar_cases) == 1


@patch("api.routes.investigate.run_investigation", new_callable=AsyncMock)
def test_investigate_endpoint(mock_run: AsyncMock, client: TestClient):
    mock_run.return_value = _sample_result()

    response = client.post(
        "/v1/investigate",
        json={"query": "Investigate Floor 3 HVAC alarm"},
        headers={"X-Trace-Id": "tr_client_provided"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"] == "tr_api_test"
    assert body["work_order_recommendation"]["action"] == "escalate_existing"
    assert body["auditor_verdict"]["pass"] is True
    assert response.headers["X-Trace-Id"] == "tr_client_provided"
    mock_run.assert_awaited_once()
    assert mock_run.await_args.kwargs["trace_id"] == "tr_client_provided"


def test_investigate_rejects_empty_query(client: TestClient):
    response = client.post("/v1/investigate", json={"query": ""})
    assert response.status_code == 422


@patch("api.routes.investigate.run_investigation", new_callable=AsyncMock)
def test_trace_id_generated_when_header_missing(mock_run: AsyncMock, client: TestClient):
    mock_run.return_value = _sample_result()

    response = client.post("/v1/investigate", json={"query": "Check alarm"})
    assert response.status_code == 200
    assert response.headers["X-Trace-Id"].startswith("tr_")
