import argparse
import asyncio

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.alarm_agent.agent import create_alarm_agent

DEFAULT_QUERY = "The HVAC alarm on Floor 3 keeps recurring. What should we do?"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the FM AgentOps AlarmAgent locally (CLI debug)."
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_QUERY,
        help="User query (default: Floor 3 HVAC demo)",
    )
    return parser.parse_args()


async def main():
    query = parse_args().query
    app_name = "fm-alarm"
    user_id = "demo-user"

    session_service = InMemorySessionService()
    runner = Runner(
        app_name=app_name,
        agent=create_alarm_agent(),
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
