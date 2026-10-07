import json
from pathlib import Path

import pytest

MOCK_DIR = Path(__file__).resolve().parents[1] / "data" / "mock"
MEMORY_DIR = Path(__file__).resolve().parents[1] / "data" / "memory"


def _load(name: str, directory: Path = MOCK_DIR) -> list | dict:
    with open(directory / name, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def issues():
    return _load("issues.json")


@pytest.fixture(scope="module")
def events():
    return _load("alarm_events.json")


@pytest.fixture(scope="module")
def emails():
    return _load("mailgun_emails.json")


@pytest.fixture(scope="module")
def alarms():
    return _load("alarms.json")


@pytest.fixture(scope="module")
def tickets():
    return _load("tickets.json")


@pytest.fixture(scope="module")
def assets():
    return _load("assets.json")


@pytest.fixture(scope="module")
def policies():
    return _load("policies.json")


@pytest.fixture(scope="module")
def cases():
    return _load("cases.json", MEMORY_DIR)


def test_issue_events_exist_in_alarm_events(issues, events):
    event_ids = {e["event_id"] for e in events}
    for issue in issues:
        for eid in issue.get("events", []):
            assert eid in event_ids, f"{eid} missing for {issue['issue_id']}"


def test_alarm_events_reference_valid_emails(events, emails):
    email_ids = {e["_id"] for e in emails}
    for event in events:
        eid = event.get("mailgun_email_id")
        if eid:
            assert eid in email_ids, f"{event['event_id']} references unknown email {eid}"


def test_alarm_work_orders_exist_in_tickets(alarms, tickets):
    ticket_ids = {t["work_order_id"] for t in tickets}
    for alarm in alarms:
        for wo in alarm.get("related_work_orders", []):
            assert wo in ticket_ids, f"{alarm['asset_id']} references unknown WO {wo}"


def test_issue_work_orders_exist_in_tickets(issues, tickets):
    ticket_ids = {t["work_order_id"] for t in tickets}
    for issue in issues:
        for wo in issue.get("linked_workorders", []):
            assert wo in ticket_ids, f"{issue['issue_id']} references unknown WO {wo}"


def test_assets_align_with_alarms(assets, alarms):
    alarm_asset_ids = {a["asset_id"] for a in alarms}
    for asset in assets:
        assert asset["asset_id"] in alarm_asset_ids


def test_demo_story_issue_is_recurring(issues):
    demo = next(i for i in issues if i["issue_id"] == "issue_demo_001")
    assert demo["event_count"] >= 3
    assert demo["asset_id"] == "AHU-3F-01"
    assert demo["floor"] == 3
    assert demo["linked_workorders"] == ["WO-2026-0142"]


def test_vav_issue_links_to_active_work_order(issues):
    vav = next(i for i in issues if i["issue_id"] == "issue_demo_003")
    assert vav["asset_id"] == "VAV-3F-12"
    assert vav["linked_workorders"] == ["WO-2026-0158"]
    assert vav["event_count"] == 2


def test_transient_issue_is_single_event(issues):
    transient = next(i for i in issues if i["issue_id"] == "issue_demo_004")
    assert transient["asset_id"] == "AHU-3F-02"
    assert transient["event_count"] == 1
    assert transient["linked_workorders"] == []


def test_floor2_issue_is_recurring_without_active_work_order(issues, tickets):
    floor2 = next(i for i in issues if i["issue_id"] == "issue_demo_005")
    assert floor2["asset_id"] == "AHU-2F-01"
    assert floor2["event_count"] >= 3
    active = {
        t["work_order_id"]
        for t in tickets
        if t["asset_id"] == "AHU-2F-01" and t["status"] in {"open", "in_progress"}
    }
    assert active == set()


def test_policy_supports_recurring_hvac_story(policies):
    policy = next(p for p in policies if p["policy_id"] == "HVAC-MNT-003")
    assert "AHU" in policy["applies_to"]
    assert any("3 times" in rule for rule in policy["rules"])


def test_open_work_order_for_demo_asset(tickets):
    wo = next(t for t in tickets if t["work_order_id"] == "WO-2026-0142")
    assert wo["asset_id"] == "AHU-3F-01"
    assert wo["status"] == "open"
    assert wo["linked_policy_id"] == "HVAC-MNT-003"


def test_cases_reference_valid_entities(cases, tickets, policies):
    ticket_ids = {t["work_order_id"] for t in tickets}
    policy_ids = {p["policy_id"] for p in policies}
    for case in cases:
        if case.get("work_order_id"):
            assert case["work_order_id"] in ticket_ids
        if case.get("policy_id"):
            assert case["policy_id"] in policy_ids


def test_registry_alarm_agent_tools():
    from tools.registry import get_tools_for_agent
    names = [t.__name__ for t in get_tools_for_agent("alarm_agent")]
    assert "search_alarm_history" in names


def test_registry_keys_match_agent_binding():
    from tools.registry import _AGENT_TOOL_NAMES, _REGISTRY
    for name in _AGENT_TOOL_NAMES["alarm_agent"]:
        assert name in _REGISTRY


def test_search_alarm_history_finds_ahu_2f_01_by_asset_id():
    from agents.alarm_agent.tools import search_alarm_history

    result = search_alarm_history(asset_id="AHU-2F-01", time_range_days=30)
    assert result["match_count"] >= 1
    issue = result["issues"][0]
    assert issue["asset_id"] == "AHU-2F-01"
    assert issue["event_count"] >= 3
    assert issue["is_recurring"] is True