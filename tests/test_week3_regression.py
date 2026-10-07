"""Week 3.4 regression: verify release gate blocks failing eval reports."""

from eval_harness.metrics.scorer import build_report
from eval_harness.release_gate.gate import evaluate_gate


def test_gate_blocks_when_broken_prompt_simulation():
    report = build_report(
        [
            {
                "case_id": "alarm_001",
                "pass": False,
                "rule_pass": False,
                "tool_call_accuracy": 1.0,
                "agent_coverage": 1.0,
                "answer_keyword_score": 0.4,
                "must_not_violations": [
                    "Answer contains forbidden phrase: create a new work order"
                ],
            }
        ]
    )
    criteria = {
        "pass_rate": ">= 0.85",
        "avg_tool_call_accuracy": ">= 0.90",
        "avg_answer_keyword_score": ">= 0.90",
        "critical_failures": "== 0",
    }
    result = evaluate_gate(report, criteria)
    assert result["pass"] is False
    assert report["pass_rate"] == 0.0
    assert report["critical_failures"] == 1


def test_gate_passes_after_prompt_restored_simulation():
    report = build_report(
        [
            {
                "case_id": "alarm_001",
                "pass": True,
                "rule_pass": True,
                "tool_call_accuracy": 1.0,
                "agent_coverage": 1.0,
                "answer_keyword_score": 1.0,
            }
        ]
    )
    criteria = {
        "pass_rate": ">= 0.85",
        "avg_tool_call_accuracy": ">= 0.90",
        "avg_answer_keyword_score": ">= 0.90",
        "critical_failures": "== 0",
    }
    result = evaluate_gate(report, criteria)
    assert result["pass"] is True
