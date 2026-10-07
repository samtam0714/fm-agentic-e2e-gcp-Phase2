"""Unit tests for PlannerAgent 3-step plans (Sprint 5 / 2.5.2)."""

from __future__ import annotations

from agents.planner_agent.agent import create_planner_agent
from agents.planner_agent.plan import (
    STEP_INVESTIGATE,
    STEP_POLICY,
    STEP_RECOMMEND,
    build_plan,
    replan_after_tool_error,
)
from agents.router_agent.classify import INTENT_ALARM, INTENT_POLICY, INTENT_WORKORDER


def test_build_plan_has_three_canonical_steps():
    plan = build_plan(INTENT_ALARM)
    assert [s.step for s in plan] == [STEP_INVESTIGATE, STEP_POLICY, STEP_RECOMMEND]
    assert [s.agent for s in plan] == ["alarm_agent", "kb_agent", "workorder_agent"]


def test_build_plan_marks_primary_by_intent():
    assert build_plan(INTENT_ALARM)[0].primary is True
    assert build_plan(INTENT_POLICY)[1].primary is True
    assert build_plan(INTENT_WORKORDER)[2].primary is True


def test_replan_after_tool_error_adds_recovery_hint():
    plan = replan_after_tool_error(
        INTENT_ALARM, failed_tool="search_policy_doc", error="timeout"
    )
    assert any("timeout" in step.goal for step in plan)
    assert any("retry" in step.goal.lower() for step in plan)


def test_create_planner_agent_name():
    agent = create_planner_agent()
    assert agent.name == "planner_agent"
