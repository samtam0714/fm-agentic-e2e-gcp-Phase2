from agents.workorder_agent.tools import recommend_work_order
from tools.registry import _AGENT_TOOL_NAMES, _REGISTRY, get_tools_for_agent


def test_recommend_work_order_escalate_existing_demo_asset():
    result = recommend_work_order(
        asset_id="AHU-3F-01",
        event_count=7,
        is_recurring=True,
        alarm_priority="P1",
        policy_ids=["HVAC-MNT-003"],
        likely_cause="clogged filter",
    )
    rec = result["recommendation"]
    assert rec["should_create"] is False
    assert rec["action"] == "escalate_existing"
    assert rec["should_update"] is True
    assert rec["priority"] == "high"
    assert result["active_work_orders"][0]["work_order_id"] == "WO-2026-0142"


def test_recommend_work_order_create_when_prior_wo_closed():
    result = recommend_work_order(
        asset_id="AHU-2F-01",
        event_count=4,
        is_recurring=True,
        alarm_priority="P2",
        policy_ids=["HVAC-MNT-001"],
        likely_cause="filter due for replacement",
    )
    rec = result["recommendation"]
    assert rec["should_create"] is True
    assert rec["action"] == "create_new"
    assert result["active_work_orders"] == []


def test_recommend_work_order_create_when_no_active_ticket():
    result = recommend_work_order(
        asset_id="AHU-3F-99",
        event_count=5,
        is_recurring=True,
        alarm_priority="P2",
        policy_ids=["HVAC-MNT-003"],
    )
    rec = result["recommendation"]
    assert rec["should_create"] is True
    assert rec["action"] == "create_new"
    assert rec["priority"] == "medium"


def test_recommend_work_order_monitor_single_transient_event():
    result = recommend_work_order(
        asset_id="AHU-3F-02",
        event_count=1,
        is_recurring=False,
        alarm_priority="P2",
        policy_ids=["HVAC-MNT-003", "HVAC-MNT-001"],
        likely_cause="transient load spike",
    )
    rec = result["recommendation"]
    assert rec["should_create"] is False
    assert rec["action"] == "no_action"
    assert "monitor" in rec["rationale"].lower()


def test_recommend_work_order_enriches_event_count_from_issue_when_zero():
    result = recommend_work_order(
        asset_id="VAV-3F-12",
        event_count=0,
        is_recurring=False,
        alarm_priority="P1",
    )
    assert result["query"]["event_count"] == 2
    rec = result["recommendation"]
    assert rec["action"] == "use_existing"
    assert result["active_work_orders"][0]["work_order_id"] == "WO-2026-0158"


def test_recommend_work_order_prefers_issue_record_over_wrong_agent_count():
    """Agent-supplied event_count must not override canonical issue record."""
    result = recommend_work_order(
        asset_id="AHU-3F-01",
        event_count=4,
        is_recurring=True,
        policy_ids=["HVAC-MNT-003"],
        likely_cause="clogged filter",
    )
    assert result["query"]["event_count"] == 7
    assert result["recommendation"]["action"] == "escalate_existing"


def test_recommend_work_order_empty_asset_id():
    result = recommend_work_order(asset_id="")
    assert result["error"] is not None
    assert result["recommendation"] is None


def test_registry_workorder_agent_tools():
    names = [t.__name__ for t in get_tools_for_agent("workorder_agent")]
    assert "recommend_work_order" in names


def test_registry_workorder_keys_match_binding():
    for name in _AGENT_TOOL_NAMES["workorder_agent"]:
        assert name in _REGISTRY
