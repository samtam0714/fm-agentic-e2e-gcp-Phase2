"""Root orchestrator - Router -> Planner -> execute-with-recovery (Sprint 5).

Phase 1 used a fixed SequentialAgent of specialists. Phase 2 Sprint 5 inserts
intent routing + dynamic planning, then runs the specialist pipeline inside a
LoopAgent so a single retryable tool failure can trigger one replan pass.

Sprint 7: USE_A2A_WORKORDER=1 swaps the in-process WorkOrder agent for a Mini
A2A remote client (timeout retry + local tool fallback).
"""

from __future__ import annotations

from google.adk.agents import LoopAgent, SequentialAgent

from agents.alarm_agent.agent import create_alarm_agent
from agents.auditor_agent.agent import create_auditor_agent
from agents.kb_agent.agent import create_kb_agent
from agents.planner_agent.agent import create_planner_agent
from agents.root_agent.recovery import create_recovery_gate_agent
from agents.router_agent.agent import create_router_agent
from agents.workorder_agent.agent import create_workorder_agent
from agents.workorder_agent.remote_a2a import (
    a2a_workorder_enabled,
    create_remote_workorder_agent,
)


def _create_workorder_node():
    if a2a_workorder_enabled():
        return create_remote_workorder_agent()
    return create_workorder_agent()


def create_specialist_pipeline() -> SequentialAgent:
    """V1 specialist spine: Alarm -> KB -> WorkOrder -> Auditor."""
    return SequentialAgent(
        name="specialist_pipeline",
        sub_agents=[
            create_alarm_agent(),
            create_kb_agent(),
            _create_workorder_node(),
            create_auditor_agent(),
        ],
    )


def create_execution_loop() -> LoopAgent:
    """Run specialists, then recovery_gate (escalate or one replan retry)."""
    return LoopAgent(
        name="execution_loop",
        max_iterations=2,
        sub_agents=[
            create_specialist_pipeline(),
            create_recovery_gate_agent(),
        ],
    )


def create_root_agent() -> SequentialAgent:
    """Phase 2 orchestrator: Router -> Planner -> execution loop."""
    return SequentialAgent(
        name="root_agent",
        sub_agents=[
            create_router_agent(),
            create_planner_agent(),
            create_execution_loop(),
        ],
    )


root_agent = create_root_agent()
