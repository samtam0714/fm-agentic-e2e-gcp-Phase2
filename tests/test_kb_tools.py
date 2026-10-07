from agents.kb_agent.tools import search_policy_doc
from tools.registry import _AGENT_TOOL_NAMES, _REGISTRY, get_tools_for_agent


def test_search_policy_doc_recurring_hvac():
    result = search_policy_doc("recurring hvac filter", asset_type="AHU")
    assert result["match_count"] >= 1
    policy_ids = {p["policy_id"] for p in result["policies"]}
    assert "HVAC-MNT-003" in policy_ids


def test_search_policy_doc_empty_query():
    result = search_policy_doc("")
    assert result["match_count"] == 0
    assert result["policies"] == []


def test_search_policy_doc_no_match():
    result = search_policy_doc("xyznotfound", asset_type="AHU")
    assert result["match_count"] == 0


def test_search_policy_doc_matches_underscored_alarm_type():
    """safety_001: underscored alarm type still matches HVAC-MNT-003."""
    result = search_policy_doc("high_supply_air_temp", asset_type="AHU")
    policy_ids = {p["policy_id"] for p in result["policies"]}
    assert "HVAC-MNT-003" in policy_ids


def test_search_policy_doc_by_policy_id():
    """Direct policy_id retrieval returns a match."""
    result = search_policy_doc("HVAC-MNT-001", asset_type="AHU")
    policy_ids = {p["policy_id"] for p in result["policies"]}
    assert "HVAC-MNT-001" in policy_ids


def test_registry_kb_agent_tools():
    names = [t.__name__ for t in get_tools_for_agent("kb_agent")]
    assert "search_policy_doc" in names


def test_registry_kb_keys_match_binding():
    for name in _AGENT_TOOL_NAMES["kb_agent"]:
        assert name in _REGISTRY
