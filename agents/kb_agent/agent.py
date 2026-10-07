import os

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.genai import types

from agents.kb_agent.prompts import SYSTEM_INSTRUCTION
from tools.registry import get_tools_for_agent

load_dotenv()

# temperature=0 keeps agent output deterministic and evaluations reproducible.
_GENERATE_CONFIG = types.GenerateContentConfig(temperature=0.0)


def create_kb_agent() -> Agent:
    return Agent(
        name="kb_agent",
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        instruction=SYSTEM_INSTRUCTION,
        tools=get_tools_for_agent("kb_agent"),
        output_key="policy_context",
        generate_content_config=_GENERATE_CONFIG,
    )


root_agent = create_kb_agent()
