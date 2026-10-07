"""Tests for versioned milestone baselines (Sprint 1 / 2.1.5)."""

from __future__ import annotations

from pathlib import Path

import yaml

from eval_harness.baselines.resolve import (
    MILESTONE_ORDER,
    latest_milestone_path,
    regression_check_rules,
    resolve_baseline_path,
)

ROOT = Path(__file__).resolve().parents[1]
BASELINES = ROOT / "eval_harness" / "baselines"
RULES = ROOT / "eval_harness" / "gates" / "regression_rules.yaml"


def test_milestone_files_exist_with_required_metadata():
    agent_required = {
        "git_sha",
        "dataset_version",
        "model",
        "model_settings",
        "google_adk_version",
        "skill_versions",
        "timestamp",
        "milestone",
    }
    retrieval_required = {
        "git_sha",
        "dataset_version",
        "google_adk_version",
        "timestamp",
        "milestone",
        "avg_recall_at_k",
        "k",
        "avg_groundedness_vector",
        "avg_groundedness_keyword",
        "groundedness_delta",
    }
    for name in MILESTONE_ORDER:
        path = BASELINES / f"{name}.json"
        assert path.exists(), f"missing milestone baseline: {path}"
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        required = retrieval_required if name == "phase2-retrieval" else agent_required
        missing = required - set(data)
        assert not missing, f"{path.name} missing metadata: {missing}"
        assert data["milestone"] == name


def test_regression_rules_point_at_active_milestone():
    rules = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    assert rules["active_milestone"] == "phase2-adk-skills"
    assert rules["baseline_path"].endswith("phase2-adk-skills.json")
    path = resolve_baseline_path(regression_rules=rules, prefer_cli=False)
    assert path.name == "phase2-adk-skills.json"
    assert path.exists()


def test_regression_check_rules_strips_config_keys():
    rules = {
        "baseline_path": "eval_harness/baselines/phase2-adk-skills.json",
        "active_milestone": "phase2-adk-skills",
        "avg_task_success_drop": "<= 0.03",
        "critical_failures_new": "<= 0",
    }
    checks = regression_check_rules(rules)
    assert "baseline_path" not in checks
    assert "active_milestone" not in checks
    assert checks["avg_task_success_drop"] == "<= 0.03"


def test_latest_milestone_is_retrieval_when_present():
    latest = latest_milestone_path()
    assert latest is not None
    assert latest.name == "phase2-retrieval.json"


def test_regression_gate_still_uses_adk_skills_baseline():
    """Agent eval regression gate must not switch to retrieval milestone."""
    rules = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    path = resolve_baseline_path(regression_rules=rules, prefer_cli=False)
    assert path.name == "phase2-adk-skills.json"
