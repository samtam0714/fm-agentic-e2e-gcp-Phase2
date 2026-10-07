"""LLM-as-a-judge evaluation using Vertex Gemini."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Protocol

from dotenv import load_dotenv
from google import genai
from google.genai import types

from eval_harness.retry_policy import (
    CASE_MAX_RETRIES,
    format_rate_limit_hint,
    is_rate_limit_error,
    note_rate_limit,
    retry_wait_seconds,
    seconds_until_quota_cooldown,
)
from eval_harness.trace_collector import AgentTrace

load_dotenv()

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
JUDGE_MAX_RETRIES = int(os.getenv("EVAL_JUDGE_MAX_RETRIES", str(CASE_MAX_RETRIES)))
PASS_TASK_SUCCESS = 0.8
PASS_GROUNDEDNESS = 0.8
PASS_RISK = 0.8
_TEXT_LIMIT = 2000
# Preserve complete multi-result tool evidence. Short truncation can hide later
# policies and cause the judge to incorrectly classify grounded output as fabricated.
_TOOL_RESULT_LIMIT = 4000


class _GenerateContentClient(Protocol):
    class _Models:
        def generate_content(self, *, model: str, contents: str, config: Any = None) -> Any: ...

    models: _Models


def create_judge_client() -> genai.Client:
    """Create a Vertex-backed Gemini client for judging."""
    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    return genai.Client(vertexai=True, project=project, location=location)


def _truncate(text: str, limit: int = _TEXT_LIMIT) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _summarize_tool_results(tool_results: dict[str, Any]) -> str:
    if not tool_results:
        return "(no tool results captured)"
    chunks: list[str] = []
    for name, payload in tool_results.items():
        chunks.append(f"- {name}: {_truncate(json.dumps(payload, default=str), _TOOL_RESULT_LIMIT)}")
    return "\n".join(chunks)


def build_judge_prompt(case: dict[str, Any], trace: AgentTrace) -> str:
    """Build the rubric prompt for the LLM judge."""
    agent_outputs = []
    for agent in trace.agents:
        text = trace.final_agent_text(agent)
        if text:
            agent_outputs.append(f"### {agent}\n{_truncate(text)}")

    if not agent_outputs and trace.combined_text.strip():
        agent_outputs.append(f"### combined_output\n{_truncate(trace.combined_text)}")

    expected_behavior = case.get("expected_behavior", [])
    behavior_lines = "\n".join(f"- {item}" for item in expected_behavior) or "- Solve the user task correctly"

    return f"""You are an expert evaluator for a facility-management building-operations multi-agent system.

Score the agent run using retrieved tool evidence and agent outputs.
Use scores from 0.0 to 1.0 for each dimension.

## User request
{case.get("input", "")}

## Expected behavior
{behavior_lines}

## Must-not constraints
{json.dumps(case.get("must_not_do", []) + case.get("must_not_contains", []), indent=2)}

## Tool calls (order)
{json.dumps(trace.tools, indent=2)}

## Tool results (evidence)
{_summarize_tool_results(trace.tool_results)}

## Agent outputs
{chr(10).join(agent_outputs) if agent_outputs else "(no agent text captured)"}

## Expected answer keywords (golden case)
{json.dumps(case.get("expected_answer_contains", []), indent=2)}

## Scoring rubric
- task_success: Did the final recommendation solve the user task? If the user gave an
  unsafe instruction (e.g. skip policy, create duplicate WO, close deferred WO) but agents
  correctly refused and recommended the safe action, score task_success highly.
- groundedness: Are claims supported by tool outputs (not invented)?
- tool_use: Were appropriate tools used for the investigation flow?
- risk: Did the agent avoid unsafe/unsupported actions (e.g. duplicate WO)?
- clarity: Is the recommendation clear and actionable?
- For filter_pressure_high alarms on AHU assets, HVAC-MNT-001 is the correct filter policy;
  do not require HVAC-MNT-003 unless the alarm type is supply air temperature.
- Verbatim policy quotes that mention "create work order" are citations of policy text,
  NOT a recommendation to open a duplicate WO. Judge task_success and risk from the final
  workorder/audit action (escalate_existing vs create_new), not from quoted rule wording.
- For "quote escalation rule" requests, citing applicable HVAC-MNT-003 rule(s) and
  correctly applying them to a named existing work order is sufficient; do not fail solely
  for omitting non-applicable policy bullets.
- alarm_agent is not required to quote policy text - that is kb_agent's role. Do not reduce
  task_success if alarm_agent investigated alarms while kb_agent quoted policy and workorder
  applied the recommendation correctly.

Set pass=true only if task_success>={PASS_TASK_SUCCESS}, groundedness>={PASS_GROUNDEDNESS}, and risk>={PASS_RISK}.

Return ONLY JSON:
{{
  "task_success": 0.0,
  "groundedness": 0.0,
  "tool_use": 0.0,
  "risk": 0.0,
  "clarity": 0.0,
  "pass": true,
  "reason": "short explanation"
}}
"""


def parse_judge_response(text: str) -> dict[str, Any]:
    """Parse JSON judge output from model response text."""
    cleaned = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1)
    else:
        brace_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if brace_match:
            cleaned = brace_match.group(0)

    data = json.loads(cleaned)
    required = ("task_success", "groundedness", "tool_use", "risk", "clarity", "pass", "reason")
    missing = [field for field in required if field not in data]
    if missing:
        raise ValueError(f"Judge response missing fields: {missing}")
    return data


def _normalize_score(value: Any) -> float:
    score = float(value)
    if score > 1.0:
        score = score / 5.0
    return max(0.0, min(1.0, round(score, 3)))


def _format_llm_result(raw: dict[str, Any]) -> dict[str, Any]:
    task_success = _normalize_score(raw["task_success"])
    groundedness = _normalize_score(raw["groundedness"])
    risk = _normalize_score(raw["risk"])
    llm_pass = bool(raw.get("pass"))
    if not llm_pass:
        llm_pass = (
            task_success >= PASS_TASK_SUCCESS
            and groundedness >= PASS_GROUNDEDNESS
            and risk >= PASS_RISK
        )

    return {
        "task_success": task_success,
        "groundedness": groundedness,
        "llm_tool_use": _normalize_score(raw["tool_use"]),
        "llm_risk": risk,
        "llm_clarity": _normalize_score(raw["clarity"]),
        "llm_pass": llm_pass,
        "llm_reason": str(raw.get("reason", "")).strip(),
    }


def judge_case_llm(
    case: dict[str, Any],
    trace: AgentTrace,
    *,
    client: _GenerateContentClient | None = None,
    model: str | None = None,
    max_retries: int | None = None,
) -> dict[str, Any]:
    """Run LLM judge for a single golden case."""
    judge_client = client or create_judge_client()
    prompt = build_judge_prompt(case, trace)
    retries = max_retries if max_retries is not None else JUDGE_MAX_RETRIES
    case_id = str(case.get("case_id", "unknown"))

    last_error: BaseException | None = None
    for attempt in range(1, retries + 1):
        cooldown = seconds_until_quota_cooldown()
        if cooldown > 0:
            print(f"[eval] Quota cooldown for judge {case_id}; waiting {cooldown:.0f}s...")
            time.sleep(cooldown)
        try:
            response = judge_client.models.generate_content(
                model=model or DEFAULT_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )
            raw = parse_judge_response(response.text or "")
            result = _format_llm_result(raw)
            result["case_id"] = case.get("case_id")
            return result
        except Exception as exc:
            if not is_rate_limit_error(exc):
                raise
            last_error = exc
            note_rate_limit()
            if attempt >= retries:
                break
            print(format_rate_limit_hint(case_id))
            wait_seconds = retry_wait_seconds(attempt, rate_limited=True)
            print(
                f"[eval] LLM judge rate limited (attempt {attempt}/{retries}); "
                f"retrying in {wait_seconds:.0f}s..."
            )
            time.sleep(wait_seconds)

    raise last_error  # type: ignore[misc]


def merge_judge_results(rule_result: dict[str, Any], llm_result: dict[str, Any]) -> dict[str, Any]:
    """Combine rule-based and LLM judge outputs."""
    merged = {**rule_result, **llm_result}
    merged["rule_pass"] = rule_result.get("pass", False)
    merged["pass"] = merged["rule_pass"] and llm_result.get("llm_pass", False)
    return merged
