"""Unit tests for RouterAgent intent classification (Sprint 5 / 2.5.1)."""

from __future__ import annotations

from agents.router_agent.agent import create_router_agent
from agents.router_agent.classify import (
    INTENT_ALARM,
    INTENT_POLICY,
    INTENT_WORKORDER,
    classify_intent,
)


def test_classify_intent_alarm_investigate():
    assert (
        classify_intent(
            "The HVAC alarm on Floor 3 keeps recurring. Check history and recommend priority."
        )
        == INTENT_ALARM
    )


def test_classify_intent_policy_lookup():
    assert (
        classify_intent(
            "What does HVAC-MNT-001 say about filter replacement for AHU units? Cite policy rules only."
        )
        == INTENT_POLICY
    )


def test_classify_intent_workorder_action():
    assert classify_intent("Escalate ticket WO-2026-0142 to high priority.") == INTENT_WORKORDER


def test_classify_intent_defaults_empty_to_alarm():
    assert classify_intent("") == INTENT_ALARM


def test_create_router_agent_name():
    agent = create_router_agent()
    assert agent.name == "router_agent"


def test_match_skill_used_by_classify():
    """Router classify delegates to Skills Registry."""
    from skills.loader import match_skill

    q = "What does HVAC-MNT-001 say about filter replacement? Cite policy only."
    assert classify_intent(q) == match_skill(q).intent
    assert match_skill(q).id == "policy-lookup"


def test_router_matches_adk_skills():
    """The Router still matches intents to canonical IDs after all skills use ADK."""
    from skills.loader import match_skill

    alarm = match_skill("Investigate the recurring alarm on AHU-3F-01.")
    assert alarm.id == "alarm-investigation"
    assert alarm.source == "adk"

    policy = match_skill(
        "What does HVAC-MNT-001 say about filter replacement? Cite policy only."
    )
    assert policy.id == "policy-lookup"
    assert policy.source == "adk"

    wo = match_skill("Escalate ticket WO-2026-0142 to high priority.")
    assert wo.id == "workorder-recommendation"
    assert wo.source == "adk"
