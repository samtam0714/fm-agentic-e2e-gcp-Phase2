import json
from pathlib import Path

import pytest

from eval_harness.golden_dataset.validate import validate_case
from eval_harness.metrics.schema import (
    CASE_CATEGORIES,
    validate_report,
)
from eval_harness.metrics.scorer import build_report

REPORTS_DIR = Path(__file__).resolve().parents[1] / "eval_harness" / "reports"


def _sample_case(**overrides) -> dict:
    base = {
        "case_id": "alarm_001",
        "pass": True,
        "case_category": "normal",
        "tool_call_accuracy": 1.0,
        "agent_coverage": 1.0,
        "answer_keyword_score": 1.0,
        "latency_seconds": 40.0,
        "task_success": 1.0,
        "groundedness": 1.0,
    }
    base.update(overrides)
    return base


def test_build_report_includes_phase2_metrics():
    report = build_report([_sample_case(), _sample_case(case_id="alarm_002", latency_seconds=60.0)])
    assert report["schema_version"] == "2.0"
    assert report["p50_latency_seconds"] == 50.0
    assert report["p95_latency_seconds"] == 59.0
    assert report["avg_tool_arg_accuracy"] is None
    assert report["avg_failure_recovery"] is None
    assert report["case_category_breakdown"]["normal"]["case_count"] == 2


def test_build_report_category_breakdown():
    report = build_report(
        [
            _sample_case(case_category="normal"),
            _sample_case(case_id="safety_001", case_category="safety", **{"pass": False}),
        ]
    )
    assert report["case_category_breakdown"]["normal"]["pass_rate"] == 1.0
    assert report["case_category_breakdown"]["safety"]["pass_rate"] == 0.0
    assert report["fail_count"] == 1


def test_validate_report_accepts_phase2_report():
    report = build_report([_sample_case()])
    assert validate_report(report) == []


def test_validate_report_rejects_missing_metrics():
    report = {"cases": [_sample_case()]}
    errors = validate_report(report)
    assert any("missing aggregate metric" in err for err in errors)


def test_validate_case_rejects_invalid_category():
    errors = validate_case(
        {
            "case_id": "bad_001",
            "input": "test",
            "expected_tools": ["search_alarm_history"],
            "expected_agents": ["alarm_agent"],
            "case_category": "invalid",
        }
    )
    assert any("case_category" in err for err in errors)


def test_validate_case_defaults_category():
    errors = validate_case(
        {
            "case_id": "alarm_001",
            "input": "test",
            "expected_tools": ["search_alarm_history"],
            "expected_agents": ["alarm_agent"],
        }
    )
    assert errors == []


@pytest.mark.parametrize("category", sorted(CASE_CATEGORIES))
def test_all_case_categories_are_valid(category: str):
    errors = validate_case(
        {
            "case_id": f"{category}_001",
            "input": "test",
            "expected_tools": ["search_alarm_history"],
            "expected_agents": ["alarm_agent"],
            "case_category": category,
        }
    )
    assert errors == []


def test_baseline_report_matches_schema():
    baseline_path = REPORTS_DIR / "baseline.json"
    assert baseline_path.exists(), "baseline.json must be frozen for regression gate"
    with open(baseline_path, encoding="utf-8") as f:
        baseline = json.load(f)
    assert validate_report(baseline) == []
    assert baseline["pass_rate"] == 1.0
    assert baseline["case_count"] >= 11
