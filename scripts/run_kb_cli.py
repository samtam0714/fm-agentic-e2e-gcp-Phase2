import asyncio
import sys

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.kb_agent.agent import create_kb_agent

DEFAULT_QUERY = (
    "AHU-3F-01 has recurring high supply air temp alarms (7 events in 30 days). "
    "What does maintenance policy say about work orders and filter replacement?"
)


async def main():
    query = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUERY
    app_name = "fm-kb"
    user_id = "demo-user"

    session_service = InMemorySessionService()
    runner = Runner(
        app_name=app_name,
        agent=create_kb_agent(),
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
