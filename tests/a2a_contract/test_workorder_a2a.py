"""A2A contract tests for Mini WorkOrder remote agent (Sprint 7 / 2.7.6)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from agents.root_agent.agent import create_specialist_pipeline
from agents.workorder_agent.a2a_client import WorkOrderA2AClient
from agents.workorder_agent.a2a_protocol import (
    A2AClientError,
    A2AMessageSendResponse,
)
from agents.workorder_agent.a2a_server import app
from agents.workorder_agent.remote_a2a import (
    RemoteWorkOrderA2AAgent,
    local_workorder_fallback,
)
from observability.tracing.span_recorder import SpanRecorder

ROOT = Path(__file__).resolve().parents[2]
AGENT_CARD = ROOT / "deployment" / "a2a" / "agent_card.json"


class _TestClientAdapter(httpx.Client):
    """Route httpx calls through Starlette TestClient (sync ASGI)."""

    def __init__(self, test_client: TestClient):
        super().__init__(base_url="http://testserver")
        self._tc = test_client

    def request(self, method, url, **kwargs):  # type: ignore[override]
        path = str(url)
        if path.startswith("http://testserver"):
            path = path[len("http://testserver") :]
        if path.startswith("http://test"):
            path = path[len("http://test") :]
        headers = kwargs.pop("headers", None) or {}
        content = kwargs.pop("content", None)
        json_body = kwargs.pop("json", None)
        if json_body is not None:
            resp = self._tc.request(method, path, headers=headers, json=json_body)
        else:
            resp = self._tc.request(method, path, headers=headers, content=content)
        return httpx.Response(
            status_code=resp.status_code,
            headers=resp.headers,
            content=resp.content,
            request=httpx.Request(method, f"http://testserver{path}"),
        )


@pytest.fixture()
def a2a_app_client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def wo_client(a2a_app_client: TestClient) -> WorkOrderA2AClient:
    return WorkOrderA2AClient(
        base_url="http://testserver",
        client=_TestClientAdapter(a2a_app_client),
        timeout_seconds=2,
    )


def test_agent_card_file_has_required_a2a_fields():
    card = json.loads(AGENT_CARD.read_text(encoding="utf-8"))
    assert card["name"]
    assert card["url"]
    assert card["skills"]
    assert card["skills"][0]["id"] == "workorder-recommendation"
    assert "capabilities" in card


def test_agent_card_endpoint(a2a_app_client: TestClient):
    resp = a2a_app_client.get("/.well-known/agent.json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"].startswith("FM AgentOps")
    assert body["skills"][0]["id"] == "workorder-recommendation"


def test_message_send_happy_path_propagates_trace_id(
    a2a_app_client: TestClient, tmp_path, monkeypatch
):
    import agents.workorder_agent.a2a_server as a2a_server

    original_init = SpanRecorder.__init__

    def _init(self, trace_id, output_dir=None):
        original_init(self, trace_id, output_dir=tmp_path)

    monkeypatch.setattr(a2a_server.SpanRecorder, "__init__", _init)

    payload = {
        "message": {
            "role": "user",
            "parts": [{"type": "text", "text": "Recommend WO for recurring AHU-3F-01"}],
            "metadata": {
                "asset_id": "AHU-3F-01",
                "event_count": 5,
                "is_recurring": True,
                "policy_ids": ["HVAC-MNT-003"],
            },
        }
    }
    resp = a2a_app_client.post(
        "/a2a/v1/message:send",
        json=payload,
        headers={"X-Trace-Id": "tr_contract_001"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("X-Trace-Id") == "tr_contract_001"
    body = A2AMessageSendResponse.model_validate(resp.json())
    assert body.trace_id == "tr_contract_001"
    assert body.task.status.state == "completed"
    assert body.task.artifacts
    text = body.task.artifacts[0].parts[0].text
    assert "action=" in text
    assert "WO-2026-0142" in text or "escalate" in text.lower() or "priority" in text

    spans_path = tmp_path / "tr_contract_001.jsonl"
    assert spans_path.exists()
    line = spans_path.read_text(encoding="utf-8").strip()
    assert "workorder-a2a" in line
    assert "a2a.message_send" in line


def test_http_client_fetch_card_and_send(wo_client: WorkOrderA2AClient):
    card = wo_client.fetch_agent_card()
    assert "WorkOrder" in card["name"]
    result = wo_client.send_message(
        text="Investigate AHU-3F-01",
        trace_id="tr_client_1",
        metadata={"asset_id": "AHU-3F-01", "event_count": 5, "is_recurring": True},
    )
    assert result.trace_id == "tr_client_1"
    assert result.task.artifacts


def test_timeout_error_is_retryable(monkeypatch, wo_client: WorkOrderA2AClient):
    monkeypatch.setenv("WORKORDER_A2A_FAULT", "timeout")
    monkeypatch.setenv("WORKORDER_A2A_TIMEOUT_SLEEP", "0")
    with pytest.raises(A2AClientError) as exc:
        wo_client.send_message(
            text="AHU-3F-01",
            trace_id="tr_to",
            metadata={"asset_id": "AHU-3F-01"},
        )
    assert exc.value.retryable is True
    assert exc.value.error in {"timeout", "unavailable"}


def test_unavailable_error(monkeypatch, wo_client: WorkOrderA2AClient):
    monkeypatch.setenv("WORKORDER_A2A_FAULT", "unavailable")
    with pytest.raises(A2AClientError) as exc:
        wo_client.send_message(
            text="AHU-3F-01",
            trace_id="tr_ua",
            metadata={"asset_id": "AHU-3F-01"},
        )
    assert exc.value.error == "unavailable"
    assert exc.value.retryable is True


def test_invalid_response_error(monkeypatch, wo_client: WorkOrderA2AClient):
    monkeypatch.setenv("WORKORDER_A2A_FAULT", "invalid")
    with pytest.raises(A2AClientError) as exc:
        wo_client.send_message(
            text="AHU-3F-01",
            trace_id="tr_inv",
            metadata={"asset_id": "AHU-3F-01"},
        )
    assert exc.value.error == "invalid_response"
    assert exc.value.retryable is False


def test_remote_agent_falls_back_locally_on_invalid(
    monkeypatch, wo_client: WorkOrderA2AClient
):
    monkeypatch.setenv("WORKORDER_A2A_FAULT", "invalid")
    agent = RemoteWorkOrderA2AAgent(client=wo_client, max_attempts=1)

    class _Session:
        state = {
            "alarm_summary": "Recurring alarm on AHU-3F-01 event_count=5",
            "policy_context": "HVAC-MNT-003 applies",
            "trace_id": "tr_fb",
        }
        events = []

    class _Ctx:
        invocation_id = "inv_fb"
        session = _Session()
        user_content = None

    async def _collect():
        events = []
        async for event in agent._run_async_impl(_Ctx()):  # noqa: SLF001
            events.append(event)
        return events

    events = asyncio.run(_collect())
    assert len(events) == 1
    text = events[0].content.parts[0].text
    assert "a2a_degraded" in text or "fallback=local" in text
    assert events[0].actions.state_delta["work_order_recommendation"]


def test_local_fallback_helper():
    text, meta = local_workorder_fallback(
        text="AHU-3F-01 recurring",
        metadata={"asset_id": "AHU-3F-01", "event_count": 5, "is_recurring": True},
    )
    assert "action=" in text
    assert meta["fallback"] == "local"


def test_root_pipeline_uses_remote_when_flag_on(monkeypatch):
    monkeypatch.setenv("USE_A2A_WORKORDER", "1")
    pipeline = create_specialist_pipeline()
    wo = pipeline.sub_agents[2]
    assert wo.name == "workorder_agent"
    assert type(wo).__name__ == "RemoteWorkOrderA2AAgent"


def test_root_pipeline_uses_local_when_flag_off(monkeypatch):
    monkeypatch.delenv("USE_A2A_WORKORDER", raising=False)
    pipeline = create_specialist_pipeline()
    wo = pipeline.sub_agents[2]
    assert wo.name == "workorder_agent"
    assert type(wo).__name__ in {"Agent", "LlmAgent"}
