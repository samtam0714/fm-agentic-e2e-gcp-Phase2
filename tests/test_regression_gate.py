"""Regression gate: block deploy when metrics degrade vs baseline."""

from eval_harness.release_gate.gate import evaluate_all_gates, evaluate_regression_gate


def _baseline() -> dict:
    return {
        "case_count": 11,
        "pass_rate": 1.0,
        "avg_task_success": 1.0,
        "avg_groundedness": 1.0,
        "critical_failures": 0,
        "p95_latency_seconds": 57.248,
        "llm_judged_cases": 11,
    }


def test_regression_gate_passes_when_matching_baseline():
    report = _baseline()
    rules = {
        "avg_task_success_drop": "<= 0.03",
        "avg_groundedness_drop": "<= 0.03",
        "pass_rate_drop": "<= 0.03",
        "p95_latency_increase": "<= 0.20",
        "critical_failures_new": "<= 0",
    }
    result = evaluate_regression_gate(_baseline(), report, rules)
    assert result["pass"] is True


def test_regression_gate_blocks_on_task_success_drop():
    report = {**_baseline(), "avg_task_success": 0.90}
    rules = {"avg_task_success_drop": "<= 0.03"}
    result = evaluate_regression_gate(_baseline(), report, rules)
    assert result["pass"] is False
    assert result["checks"]["avg_task_success_drop"]["actual"] == 0.1


def test_regression_gate_blocks_on_latency_increase():
    report = {**_baseline(), "p95_latency_seconds": 80.0}
    rules = {"p95_latency_increase": "<= 0.20"}
    result = evaluate_regression_gate(_baseline(), report, rules)
    assert result["pass"] is False
    assert result["checks"]["p95_latency_increase"]["actual"] > 0.20


def test_regression_gate_blocks_on_new_critical_failures():
    report = {**_baseline(), "critical_failures": 2}
    rules = {"critical_failures_new": "<= 0"}
    result = evaluate_regression_gate(_baseline(), report, rules)
    assert result["pass"] is False


def test_all_gates_pass_with_identical_report():
    report = _baseline()
    absolute = {
        "pass_rate": ">= 0.85",
        "avg_task_success": ">= 0.85",
        "avg_groundedness": ">= 0.90",
        "critical_failures": "== 0",
    }
    regression = {"avg_task_success_drop": "<= 0.03", "critical_failures_new": "<= 0"}
    result = evaluate_all_gates(
        report,
        absolute_criteria=absolute,
        baseline=_baseline(),
        regression_rules=regression,
    )
    assert result["pass"] is True


def test_all_gates_block_when_absolute_fails_but_regression_passes():
    report = {
        **_baseline(),
        "pass_rate": 0.5,
        "critical_failures": 3,
    }
    absolute = {"pass_rate": ">= 0.85", "critical_failures": "== 0"}
    regression = {"pass_rate_drop": "<= 0.03"}
    result = evaluate_all_gates(
        report,
        absolute_criteria=absolute,
        baseline=_baseline(),
        regression_rules=regression,
    )
    assert result["absolute"]["pass"] is False
    assert result["regression"]["pass"] is False
    assert result["pass"] is False


def test_regression_gate_allows_small_latency_increase():
    report = {**_baseline(), "p95_latency_seconds": 65.0}
    rules = {"p95_latency_increase": "<= 0.20"}
    result = evaluate_regression_gate(_baseline(), report, rules)
    assert result["pass"] is True
