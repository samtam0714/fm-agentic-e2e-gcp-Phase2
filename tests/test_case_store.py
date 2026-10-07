"""Unit tests for long-term case memory."""

from memory.case_store import CaseStore
from memory.tools import search_similar_cases


def test_get_by_asset_id_finds_demo_case():
    store = CaseStore.default()
    cases = store.get_by_asset_id("AHU-3F-01")
    assert len(cases) >= 1
    assert cases[0]["case_id"] == "case_002"
    assert cases[0]["work_order_id"] == "WO-2026-0142"


def test_search_by_keywords_finds_filter_cases():
    store = CaseStore.default()
    cases = store.search_by_keywords(["filter", "recurring"], limit=5)
    assert len(cases) >= 2
    asset_ids = {case["asset_id"] for case in cases}
    assert "AHU-2F-01" in asset_ids or "AHU-3F-01" in asset_ids


def test_search_similar_prefers_asset_id_match():
    store = CaseStore.default()
    cases = store.search_similar(asset_id="AHU-3F-01", limit=3)
    assert cases[0]["case_id"] == "case_002"


def test_search_similar_cases_tool():
    result = search_similar_cases(asset_id="AHU-3F-01", limit=2)
    assert result["match_count"] >= 1
    assert result["cases"][0]["asset_id"] == "AHU-3F-01"


def test_registry_alarm_agent_has_memory_tool():
    from tools.registry import get_tools_for_agent

    names = [t.__name__ for t in get_tools_for_agent("alarm_agent")]
    assert "search_similar_cases" in names
