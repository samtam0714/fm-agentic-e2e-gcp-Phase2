from eval_harness.release_gate.gate import evaluate_gate


def test_release_gate_passes():
    report = {
        "pass_rate": 1.0,
        "avg_tool_call_accuracy": 1.0,
        "avg_answer_keyword_score": 1.0,
        "avg_task_success": 0.9,
        "avg_groundedness": 0.92,
        "critical_failures": 0,
    }
    criteria = {
        "pass_rate": ">= 0.85",
        "avg_tool_call_accuracy": ">= 0.90",
        "avg_answer_keyword_score": ">= 0.90",
        "avg_task_success": ">= 0.85",
        "avg_groundedness": ">= 0.90",
        "critical_failures": "== 0",
    }
    result = evaluate_gate(report, criteria)
    assert result["pass"] is True


def test_release_gate_blocks_on_failures():
    report = {
        "pass_rate": 0.5,
        "avg_tool_call_accuracy": 0.5,
        "avg_answer_keyword_score": 0.5,
        "critical_failures": 1,
    }
    criteria = {
        "pass_rate": ">= 0.85",
        "critical_failures": "== 0",
    }
    result = evaluate_gate(report, criteria)
    assert result["pass"] is False
