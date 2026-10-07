import asyncio
import sys

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.auditor_agent.agent import create_auditor_agent

DEFAULT_QUERY = """Audit this combined recommendation:

Alarm: AHU-3F-01 on Floor 3, 7 recurring high supply air temp events in 30 days,
issue_demo_001, likely cause clogged filter, P1 priority.

Policy: HVAC-MNT-003 and HVAC-MNT-001 cited. Work order required when >3 events in 30 days.

Work order: escalate_existing WO-2026-0142 from medium to high priority;
should_create=false, should_update=true.

Verify groundedness and policy compliance.
"""


async def main():
    query = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUERY
    app_name = "fm-auditor"
    user_id = "demo-user"

    session_service = InMemorySessionService()
    runner = Runner(
        app_name=app_name,
        agent=create_auditor_agent(),
        session_service=session_service,
        auto_create_session=True,
    )

    session = await session_service.create_session(
        app_name=app_name, user_id=user_id
    )

    print(f"\n[user]: {query}\n")
    content = types.Content(role="user", parts=[types.Part(text=query)])

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=content,
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.function_response:
                    print(f"[tool result]: {part.function_response.name} -> ...")
                if part.text:
                    print(f"[{event.author}]: {part.text}")
                if part.function_call:
                    print(f"[tool call]: {part.function_call.name}({part.function_call.args})")


if __name__ == "__main__":
    asyncio.run(main())
