"""Run one golden case through the root-agent pipeline and collect judge traces."""

from __future__ import annotations

from eval_harness.fault_injection import fault_injection_context
from eval_harness.trace_collector import AgentTrace
from services.investigate import run_investigation


async def run_case(
    query: str,
    app_name: str = "fm-eval",
    *,
    trace_id: str | None = None,
    persist_session: bool = True,
    golden_case: dict | None = None,
) -> AgentTrace:
    """Run an investigation, enabling configured fault injection for the case."""
    with fault_injection_context(golden_case):
        result = await run_investigation(
            query,
            app_name=app_name,
            user_id="eval-user",
            trace_id=trace_id,
            persist_session=persist_session,
        )
    return result.to_agent_trace()
