from google.adk.agents import LoopAgent, SequentialAgent

from agents.root_agent.agent import (
    create_execution_loop,
    create_root_agent,
    create_specialist_pipeline,
)


def test_root_agent_starts_with_router_and_planner():
    root = create_root_agent()
    assert isinstance(root, SequentialAgent)
    names = [agent.name for agent in root.sub_agents]
    assert names == ["router_agent", "planner_agent", "execution_loop"]


def test_specialist_pipeline_order_unchanged():
    pipeline = create_specialist_pipeline()
    names = [agent.name for agent in pipeline.sub_agents]
    assert names == [
        "alarm_agent",
        "kb_agent",
        "workorder_agent",
        "auditor_agent",
    ]


def test_specialist_pipeline_output_keys():
    pipeline = create_specialist_pipeline()
    output_keys = [getattr(agent, "output_key", None) for agent in pipeline.sub_agents]
    assert output_keys == [
        "alarm_summary",
        "policy_context",
        "work_order_recommendation",
        "auditor_verdict",
    ]


def test_execution_loop_has_recovery_gate():
    loop = create_execution_loop()
    assert isinstance(loop, LoopAgent)
    assert loop.max_iterations == 2
    names = [agent.name for agent in loop.sub_agents]
    assert names == ["specialist_pipeline", "recovery_gate"]
