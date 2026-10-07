"""Unit tests for session memory snapshots."""

import asyncio
from pathlib import Path

from google.adk.sessions import InMemorySessionService

from memory.case_store import CaseStore
from memory.session_store import (
    build_session_snapshot,
    capture_session_memory,
    enrich_similar_cases,
    extract_asset_id,
    persist_session_snapshot,
)


def test_extract_asset_id_from_alarm_summary():
    text = "Recurring P1 alarm for AHU-3F-01 on Floor 3."
    assert extract_asset_id(text) == "AHU-3F-01"


def test_build_session_snapshot_collects_agent_keys():
    state = {
        "alarm_summary": "AHU-3F-01 recurring alarm",
        "policy_context": "HVAC-MNT-003 applies",
        "work_order_recommendation": "escalate WO-2026-0142",
        "auditor_verdict": "pass: yes",
    }
    snapshot = build_session_snapshot(
        state,
        trace_id="tr_test",
        session_id="sess_test",
    )
    assert snapshot["trace_id"] == "tr_test"
    assert snapshot["session_id"] == "sess_test"
    assert snapshot["alarm_summary"] == state["alarm_summary"]
    assert snapshot["similar_cases"] == []


def test_enrich_similar_cases_adds_asset_matches():
    snapshot = {
        "alarm_summary": "Investigating recurring alarm on AHU-3F-01 floor 3 filter issue.",
    }
    enriched = enrich_similar_cases(snapshot, CaseStore.default())
    assert len(enriched["similar_cases"]) >= 1
    assert enriched["similar_cases"][0]["asset_id"] == "AHU-3F-01"


def test_enrich_similar_cases_uses_semantic_query_without_asset():
    """Sprint 6: session snapshot query path, not keyword-only."""
    snapshot = {
        "alarm_summary": "clogged AHU filter making building overheat",
    }
    enriched = enrich_similar_cases(snapshot, CaseStore.default())
    ids = {c["case_id"] for c in enriched["similar_cases"]}
    assert "case_001" in ids


def test_persist_session_snapshot_writes_json(tmp_path: Path):
    snapshot = {
        "session_id": "sess_unit",
        "trace_id": "tr_unit",
        "alarm_summary": "test",
        "similar_cases": [],
    }
    path = persist_session_snapshot(snapshot, output_dir=tmp_path)
    assert path.exists()
    assert path.name == "sess_unit.json"


def test_capture_session_memory(tmp_path: Path):
    async def _run() -> None:
        session_service = InMemorySessionService()
        session = await session_service.create_session(
            app_name="test-app",
            user_id="test-user",
            state={
                "alarm_summary": "Active recurring issue on AHU-3F-01 with clogged filter.",
                "policy_context": "policy found",
            },
        )

        snapshot, path = await capture_session_memory(
            session_service,
            app_name="test-app",
            user_id="test-user",
            session_id=session.id,
            trace_id="tr_capture",
            persist=True,
            output_dir=tmp_path,
        )

        assert snapshot["alarm_summary"].startswith("Active recurring")
        assert snapshot["policy_context"] == "policy found"
        assert len(snapshot["similar_cases"]) >= 1
        assert path is not None
        assert path.exists()

    asyncio.run(_run())
