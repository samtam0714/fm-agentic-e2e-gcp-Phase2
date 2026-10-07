from agents.auditor_agent.tools import audit_recommendation
from tools.registry import _AGENT_TOOL_NAMES, _REGISTRY, get_tools_for_agent


def test_audit_recommendation_passes_valid_escalation():
    result = audit_recommendation(
        asset_id="AHU-3F-01",
        event_count=7,
        is_recurring=True,
        policy_ids=["HVAC-MNT-003", "HVAC-MNT-001"],
        work_order_action="escalate_existing",
        should_create=False,
        cited_likely_cause="clogged filter",
        alarm_issue_id="issue_demo_001",
    )
    assert result["grounded"] is True
    assert result["pass"] is True
    assert result["violations"] == []
    assert result["must_not_violations"] == []


def test_audit_recommendation_fails_create_without_policy():
    result = audit_recommendation(
        asset_id="AHU-3F-01",
        event_count=7,
        is_recurring=True,
        policy_ids=[],
        work_order_action="create_new",
        should_create=True,
        cited_likely_cause="clogged filter",
        alarm_issue_id="issue_demo_001",
    )
    assert result["pass"] is False
    assert len(result["must_not_violations"]) >= 1


def test_audit_recommendation_fails_wrong_event_count():
    result = audit_recommendation(
        asset_id="AHU-3F-01",
        event_count=2,
        is_recurring=True,
        policy_ids=["HVAC-MNT-003"],
        work_order_action="escalate_existing",
        should_create=False,
        cited_likely_cause="clogged filter",
        alarm_issue_id="issue_demo_001",
    )
    assert result["grounded"] is False
    assert result["pass"] is False


def test_audit_recommendation_passes_create_when_linked_wo_closed():
    result = audit_recommendation(
        asset_id="AHU-2F-01",
        event_count=5,
        is_recurring=True,
        policy_ids=["HVAC-MNT-003", "HVAC-MNT-001"],
        work_order_action="create_new",
        should_create=True,
        cited_likely_cause="filter due for replacement",
        alarm_issue_id="issue_demo_005",
    )
    assert result["grounded"] is True
    assert result["pass"] is True
    assert result["must_not_violations"] == []


def test_audit_recommendation_passes_filter_pressure_with_mnt001_only():
    result = audit_recommendation(
        asset_id="AHU-2F-01",
        event_count=5,
        is_recurring=True,
        policy_ids=["HVAC-MNT-001"],
        work_order_action="create_new",
        should_create=True,
        cited_likely_cause="filter due for replacement",
        alarm_issue_id="issue_demo_005",
    )
    assert result["grounded"] is True
    assert result["pass"] is True


def test_audit_recommendation_fails_close_on_recurring_p1():
    result = audit_recommendation(
        asset_id="AHU-3F-01",
        event_count=7,
        is_recurring=True,
        policy_ids=["HVAC-MNT-003"],
        work_order_action="close_existing",
        should_create=False,
        cited_likely_cause="clogged filter",
        alarm_issue_id="issue_demo_001",
    )
    assert result["pass"] is False
    assert any("Dismiss recurring" in v for v in result["must_not_violations"])


def test_audit_recommendation_fails_duplicate_create():
    result = audit_recommendation(
        asset_id="AHU-3F-01",
        event_count=7,
        is_recurring=True,
        policy_ids=["HVAC-MNT-003"],
        work_order_action="create_new",
        should_create=True,
        cited_likely_cause="clogged filter",
        alarm_issue_id="issue_demo_001",
    )
    assert result["pass"] is False
    assert any("linked work orders" in v for v in result["must_not_violations"])


def test_registry_auditor_agent_tools():
    names = [t.__name__ for t in get_tools_for_agent("auditor_agent")]
    assert "audit_recommendation" in names


def test_registry_auditor_keys_match_binding():
    for name in _AGENT_TOOL_NAMES["auditor_agent"]:
        assert name in _REGISTRY
