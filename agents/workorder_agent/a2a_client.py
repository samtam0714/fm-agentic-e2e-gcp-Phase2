"""HTTP client for the remote WorkOrder Mini A2A service (Sprint 7)."""

from __future__ import annotations

import os
from typing import Any

import httpx

from agents.workorder_agent.a2a_protocol import (
    AGENT_CARD_PATH,
    DEFAULT_A2A_BASE_URL,
    MESSAGE_SEND_PATH,
    TRACE_HEADER,
    A2AClientError,
    A2AMessage,
    A2AMessageSendRequest,
    A2AMessageSendResponse,
    A2ATextPart,
)


def a2a_base_url() -> str:
    return os.getenv("WORKORDER_A2A_URL", DEFAULT_A2A_BASE_URL).rstrip("/")


def a2a_timeout_seconds() -> float:
    return float(os.getenv("WORKORDER_A2A_TIMEOUT_SECONDS", "3"))


class WorkOrderA2AClient:
    """Thin HTTP+JSON client for agent card + message:send."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url or a2a_base_url()).rstrip("/")
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else a2a_timeout_seconds()
        )
        self._transport = transport
        self._external_client = client

    def _client(self) -> httpx.Client:
        if self._external_client is not None:
            return self._external_client
        return httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            transport=self._transport,
        )

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if self._external_client is not None:
            url = path if path.startswith("http") else f"{self.base_url}{path}"
            return self._external_client.request(method, url, **kwargs)
        with self._client() as client:
            return client.request(method, path, **kwargs)

    def fetch_agent_card(self) -> dict[str, Any]:
        try:
            resp = self._request("GET", AGENT_CARD_PATH)
        except httpx.TimeoutException as exc:
            raise A2AClientError(
                error="timeout",
                retryable=True,
                message=f"agent card timeout: {exc}",
            ) from exc
        except httpx.HTTPError as exc:
            raise A2AClientError(
                error="unavailable",
                retryable=True,
                message=f"agent card unreachable: {exc}",
            ) from exc
        if resp.status_code >= 500:
            raise A2AClientError(
                error="unavailable",
                retryable=True,
                message=f"agent card HTTP {resp.status_code}",
                status_code=resp.status_code,
            )
        if resp.status_code >= 400:
            raise A2AClientError(
                error="invalid_response",
                retryable=False,
                message=f"agent card HTTP {resp.status_code}",
                status_code=resp.status_code,
            )
        try:
            data = resp.json()
        except Exception as exc:
            raise A2AClientError(
                error="invalid_response",
                retryable=False,
                message=f"agent card is not JSON: {exc}",
            ) from exc
        if not isinstance(data, dict) or "name" not in data:
            raise A2AClientError(
                error="invalid_response",
                retryable=False,
                message="agent card missing required fields",
            )
        return data

    def send_message(
        self,
        *,
        text: str,
        trace_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> A2AMessageSendResponse:
        meta = dict(metadata or {})
        meta.setdefault("trace_id", trace_id)
        request = A2AMessageSendRequest(
            message=A2AMessage(
                role="user",
                parts=[A2ATextPart(text=text)],
                metadata=meta,
            )
        )
        headers = {TRACE_HEADER: trace_id}
        try:
            resp = self._request(
                "POST",
                MESSAGE_SEND_PATH,
                json=request.model_dump(),
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise A2AClientError(
                error="timeout",
                retryable=True,
                message=f"message:send timeout: {exc}",
            ) from exc
        except httpx.HTTPError as exc:
            raise A2AClientError(
                error="unavailable",
                retryable=True,
                message=f"message:send unreachable: {exc}",
            ) from exc

        if resp.status_code in {502, 503, 504}:
            raise A2AClientError(
                error="unavailable" if resp.status_code != 504 else "timeout",
                retryable=True,
                message=f"message:send HTTP {resp.status_code}: {resp.text[:200]}",
                status_code=resp.status_code,
            )
        if resp.status_code >= 400:
            raise A2AClientError(
                error="invalid_response",
                retryable=False,
                message=f"message:send HTTP {resp.status_code}: {resp.text[:200]}",
                status_code=resp.status_code,
            )

        try:
            data = resp.json()
            parsed = A2AMessageSendResponse.model_validate(data)
        except Exception as exc:
            raise A2AClientError(
                error="invalid_response",
                retryable=False,
                message=f"invalid A2A response body: {exc}",
                status_code=resp.status_code,
            ) from exc

        if parsed.task.status.state not in {"completed", "working", "submitted"}:
            raise A2AClientError(
                error="invalid_response",
                retryable=False,
                message=f"unexpected task state: {parsed.task.status.state}",
            )
        if not parsed.task.artifacts:
            raise A2AClientError(
                error="invalid_response",
                retryable=False,
                message="A2A response missing artifacts",
            )
        # Prefer response header / body trace_id continuity
        if not parsed.trace_id:
            parsed.trace_id = resp.headers.get(TRACE_HEADER, trace_id)
        return parsed
