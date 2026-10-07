"""ADK session state helpers and snapshot persistence."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from google.adk.sessions import InMemorySessionService

from memory.case_store import CaseStore

SESSION_KEYS = (
    "trace_id",
    "session_id",
    "route_intent",
    "execution_plan",
    "plan_summary",
    "alarm_summary",
    "policy_context",
    "work_order_recommendation",
    "auditor_verdict",
    "similar_cases",
)

DEFAULT_SESSIONS_DIR = (
    Path(__file__).resolve().parents[1] / "data" / "memory" / "sessions"
)

_ASSET_ID_PATTERN = re.compile(
    r"\b(?:AHU|VAV|RTU|FCU)-[\w-]+\b",
    re.IGNORECASE,
)


def extract_asset_id(*texts: str | None) -> str | None:
    """Extract the first asset ID from free-form agent text."""
    for text in texts:
        if not text:
            continue
        match = _ASSET_ID_PATTERN.search(str(text))
        if match:
            return match.group(0).upper()
    return None


def build_session_snapshot(
    state: dict[str, Any],
    *,
    trace_id: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    """Build a normalized memory snapshot from ADK session state."""
    snapshot: dict[str, Any] = {
        "trace_id": trace_id,
        "session_id": session_id,
    }
    for key in SESSION_KEYS:
        if key in ("trace_id", "session_id"):
            continue
        if key in state:
            snapshot[key] = state[key]
    if "similar_cases" not in snapshot:
        snapshot["similar_cases"] = []
    return snapshot


def enrich_similar_cases(
    snapshot: dict[str, Any],
    case_store: CaseStore | None = None,
    *,
    limit: int = 3,
) -> dict[str, Any]:
    """Attach similar historical cases based on alarm context."""
    store = case_store or CaseStore.default()
    alarm_summary = snapshot.get("alarm_summary", "")
    asset_id = extract_asset_id(str(alarm_summary) if alarm_summary else None)

    keywords: list[str] = []
    alarm_text = str(alarm_summary).lower()
    for token in ("recurring", "filter", "hvac", "temperature", "floor 3"):
        if token in alarm_text:
            keywords.append(token)

    similar = store.search_similar(
        asset_id=asset_id,
        keywords=keywords or None,
        query=str(alarm_summary) if alarm_summary else None,
        limit=limit,
    )
    snapshot["similar_cases"] = similar
    return snapshot


def persist_session_snapshot(
    snapshot: dict[str, Any],
    output_dir: Path | None = None,
) -> Path:
    """Write session memory snapshot to data/memory/sessions/{session_id}.json."""
    sessions_dir = output_dir or DEFAULT_SESSIONS_DIR
    sessions_dir.mkdir(parents=True, exist_ok=True)

    session_id = snapshot.get("session_id") or "unknown_session"
    path = sessions_dir / f"{session_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)
    return path


async def capture_session_memory(
    session_service: InMemorySessionService,
    *,
    app_name: str,
    user_id: str,
    session_id: str,
    trace_id: str = "",
    case_store: CaseStore | None = None,
    persist: bool = True,
    output_dir: Path | None = None,
) -> tuple[dict[str, Any], Path | None]:
    """Read ADK session state, enrich with similar cases, optionally persist."""
    session = await session_service.get_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    state = dict(session.state) if session else {}

    snapshot = build_session_snapshot(
        state,
        trace_id=trace_id,
        session_id=session_id,
    )
    enrich_similar_cases(snapshot, case_store=case_store)

    path = None
    if persist:
        path = persist_session_snapshot(snapshot, output_dir=output_dir)
    return snapshot, path
