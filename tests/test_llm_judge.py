"""Unit tests for LLM judge."""

from __future__ import annotations

import json

import pytest

from eval_harness.judges.llm_judge import (
    build_judge_prompt,
    judge_case_llm,
    merge_judge_results,
    parse_judge_response,
)
from eval_harness.judges.rule_based_judge import judge_case
from eval_harness.trace_collector import AgentTrace


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModels:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def generate_content(self, *, model: str, contents: str, config=None) -> _FakeResponse:
        return _FakeResponse(json.dumps(self.payload))


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self.models = _FakeModels(payload)


def _sample_trace() -> AgentTrace:
    trace = AgentTrace()
    trace.agents = ["alarm_agent", "kb_agent", "workorder_agent", "auditor_agent"]
    trace.tools = [
        "search_alarm_history",
        "search_policy_doc",
        "recommend_work_order",
        "audit_recommendation",
    ]
    trace.texts_by_agent = {
        "alarm_agent": ["AHU-3F-01 has 7 recurring events. Likely clogged filter."],
        "kb_agent": ["Policy HVAC-MNT-003 requires work order after 3 recurrences."],
        "workorder_agent": ["Escalate existing WO-2026-0142 to high priority."],
        "auditor_agent": ["grounded: yes pass: yes"],
    }
    trace.combined_text = "\n".join(
        t for texts in trace.texts_by_agent.values() for t in texts
    )
    trace.tool_results = {
        "search_alarm_history": {"issues": [{"asset_id": "AHU-3F-01", "event_count": 7}]},
        "recommend_work_order": {
            "recommendation": {"action": "escalate_existing", "should_create": False}
        },
    }
    return trace


def _sample_case() -> dict:
    return {
        "case_id": "alarm_001",
        "input": "Investigate recurring Floor 3 HVAC alarm and recommend work order action.",
        "expected_tools": ["search_alarm_history", "search_policy_doc", "recommend_work_order"],
        "expected_agents": ["alarm_agent", "kb_agent", "workorder_agent", "auditor_agent"],
        "expected_answer_contains": ["AHU-3F-01", "WO-2026-0142", "escalate"],
        "expected_behavior": ["Escalate existing WO-2026-0142"],
        "must_not_contains": ["create a new work order"],
    }


def test_build_judge_prompt_includes_case_and_trace():
    prompt = build_judge_prompt(_sample_case(), _sample_trace())
    assert "alarm_001" not in prompt  # case_id not required in prompt body
    assert "AHU-3F-01" in prompt
    assert "search_alarm_history" in prompt
    assert "Escalate existing WO-2026-0142" in prompt
    assert "verbatim policy quotes" in prompt.lower()


def test_build_judge_prompt_rag004_escalation_guidance():
    case = {
        "case_id": "rag_004",
        "input": "Quote the exact escalation rule from HVAC-MNT-003 for recurring supply air temperature alarms on AHU-3F-01 and apply it to WO-2026-0142.",
        "expected_behavior": [
            "Retrieve and cite applicable HVAC-MNT-003 escalation/priority rules verbatim",
            "Apply policy to escalate existing WO-2026-0142 (not create duplicate)",
        ],
        "must_not_contains": ["create a new work order"],
    }
    prompt = build_judge_prompt(case, _sample_trace())
    assert "quote escalation rule" in prompt.lower()
    assert "escalate_existing" in prompt


def test_judge_prompt_does_not_truncate_multi_policy_evidence():
    """Judge evidence preserves later policies from multi-result searches.

    This protects rag_005, where HVAC-MNT-001 appears second and the former
    800-character truncation caused grounded policy rules to look fabricated.
    """
    trace = _sample_trace()
    trace.tool_results = {
        "search_policy_doc": {
            "query": {"query": "filter replacement", "asset_type": "AHU"},
            "match_count": 2,
            "policies": [
                {
                    "policy_id": "HVAC-MNT-003",
                    "title": "Recurring HVAC Temperature Alarm Response",
                    "applies_to": ["AHU", "VAV"],
                    "summary": "For recurring supply air temperature alarms " * 8,
                    "rules": ["Create work order if alarm recurs more than 3 times in 30 days"] * 4,
                    "keywords": ["recurring", "hvac", "filter", "supply air temp", "work order"],
                },
                {
                    "policy_id": "HVAC-MNT-001",
                    "title": "Standard Filter Replacement Schedule",
                    "applies_to": ["AHU"],
                    "summary": "Replace AHU filters every 90 days or when filter pressure alarm occurs.",
                    "rules": [
                        "Scheduled PM every 90 days",
                        "Emergency replacement allowed for recurring temperature alarms",
                    ],
                    "keywords": ["filter", "replacement", "PM", "AHU"],
                },
            ],
        }
    }
    prompt = build_judge_prompt(_sample_case(), trace)
    assert "HVAC-MNT-001" in prompt
    assert "Scheduled PM every 90 days" in prompt


def test_parse_judge_response_from_json_block():
    text = """```json
    {"task_success": 0.9, "groundedness": 0.95, "tool_use": 0.9, "risk": 1.0, "clarity": 0.85, "pass": true, "reason": "ok"}
    ```"""
    parsed = parse_judge_response(text)
    assert parsed["task_success"] == 0.9
    assert parsed["pass"] is True


class _FlakyModels:
    def __init__(self, payload: dict, *, fail_times: int = 0) -> None:
        self.payload = payload
        self.fail_times = fail_times
        self.calls = 0

    def generate_content(self, *, model: str, contents: str, config=None) -> _FakeResponse:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return _FakeResponse(json.dumps(self.payload))


class _FlakyClient:
    def __init__(self, payload: dict, *, fail_times: int = 0) -> None:
        self.models = _FlakyModels(payload, fail_times=fail_times)


def test_judge_case_llm_retries_on_rate_limit(monkeypatch):
    payload = {
        "task_success": 0.9,
        "groundedness": 0.9,
        "tool_use": 0.9,
        "risk": 0.9,
        "clarity": 0.9,
        "pass": True,
        "reason": "ok",
    }
    sleeps: list[float] = []
    monkeypatch.setattr(
        "eval_harness.judges.llm_judge.note_rate_limit",
        lambda: None,
    )
    monkeypatch.setattr(
        "eval_harness.judges.llm_judge.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )
    monkeypatch.setattr(
        "eval_harness.judges.llm_judge.seconds_until_quota_cooldown",
        lambda: 0.0,
    )
    monkeypatch.setattr(
        "eval_harness.judges.llm_judge.retry_wait_seconds",
        lambda attempt, rate_limited=False: 5.0 * attempt,
    )
    client = _FlakyClient(payload, fail_times=2)
    result = judge_case_llm(
        _sample_case(),
        _sample_trace(),
        client=client,
        max_retries=3,
    )
    assert result["llm_pass"] is True
    assert client.models.calls == 3
    assert sleeps == [5, 10]


def test_judge_case_llm_with_fake_client():
    payload = {
        "task_success": 0.92,
        "groundedness": 0.9,
        "tool_use": 0.88,
        "risk": 0.95,
        "clarity": 0.9,
        "pass": True,
        "reason": "Grounded escalation recommendation.",
    }
    result = judge_case_llm(_sample_case(), _sample_trace(), client=_FakeClient(payload))
    assert result["task_success"] == 0.92
    assert result["groundedness"] == 0.9
    assert result["llm_pass"] is True
    assert "Grounded" in result["llm_reason"]


def test_judge_case_llm_normalizes_five_point_scale():
    payload = {
        "task_success": 4,
        "groundedness": 5,
        "tool_use": 4,
        "risk": 5,
        "clarity": 4,
        "pass": True,
        "reason": "good",
    }
    result = judge_case_llm(_sample_case(), _sample_trace(), client=_FakeClient(payload))
    assert result["task_success"] == 0.8
    assert result["groundedness"] == 1.0


def test_merge_judge_results_combines_pass_flags():
    rule = judge_case(_sample_case(), _sample_trace())
    llm = {
        "task_success": 0.9,
        "groundedness": 0.9,
        "llm_pass": True,
        "llm_reason": "ok",
    }
    merged = merge_judge_results(rule, llm)
    assert merged["rule_pass"] is True
    assert merged["llm_pass"] is True
    assert merged["pass"] is True


def test_merge_judge_results_fails_when_llm_fails():
    rule = judge_case(_sample_case(), _sample_trace())
    llm = {
        "task_success": 0.4,
        "groundedness": 0.5,
        "llm_pass": False,
        "llm_reason": "unsupported recommendation",
    }
    merged = merge_judge_results(rule, llm)
    assert merged["rule_pass"] is True
    assert merged["llm_pass"] is False
    assert merged["pass"] is False


def test_parse_judge_response_missing_field_raises():
    with pytest.raises(ValueError, match="missing fields"):
        parse_judge_response('{"task_success": 0.9}')
