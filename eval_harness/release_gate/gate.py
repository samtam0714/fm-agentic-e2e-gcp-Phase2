#!/usr/bin/env python3
"""
Release Gate

An evaluation run produces a scorecard (eval_report.json).
This module determines whether those results are suitable for release.

It performs two checks:
1. Absolute thresholds -- whether the scores are high enough (for example, pass rate >= 85%)
2. Regression comparison -- whether results are significantly worse than the frozen baseline

Both checks must pass to allow a release; either check can block it.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Callable

# Default rule files and baseline scorecard
GATES_DIR = Path(__file__).resolve().parents[1] / "gates"
DEFAULT_ABSOLUTE_RULES = GATES_DIR / "absolute_rules.yaml"      # Minimum scores
DEFAULT_REGRESSION_RULES = GATES_DIR / "regression_rules.yaml"  # Maximum regression
# Legacy sync copy; prefer baselines/* via regression_rules.yaml baseline_path.
DEFAULT_BASELINE = Path(__file__).resolve().parents[1] / "reports" / "baseline.json"

# These metrics come from the LLM judge; skip them when that judge did not run.
LLM_METRICS = frozenset({"avg_task_success", "avg_groundedness"})

RegressionComputer = Callable[[dict[str, Any], dict[str, Any]], float | int | None]


def _parse_criterion(value: str, actual: float | int) -> bool:
    """
    Determine whether an actual score satisfies a rule.

    YAML rules use expressions such as ">= 0.85", "<= 0.03", and "== 0".
    For example, with ">= 0.85", an actual value of 1.0 passes and 0.5 fails.
    """
    match = re.match(r"(>=|<=|==|>|<)\s*([\d.]+)", value.strip())
    if not match:
        raise ValueError(f"Invalid criterion format: {value}")
    op, threshold_str = match.groups()
    threshold = float(threshold_str)
    if op == ">=":
        return actual >= threshold
    if op == "<=":
        return actual <= threshold
    if op == "==":
        return actual == threshold
    if op == ">":
        return actual > threshold
    if op == "<":
        return actual < threshold
    raise ValueError(f"Unknown operator: {op}")


def _regression_computers() -> dict[str, RegressionComputer]:
    """
    Build comparison functions that measure differences from the baseline.

    The regression gate measures deterioration rather than absolute score quality.
    Each metric has its own algorithm, registered here by name.
    """

    def _drop(baseline_key: str) -> RegressionComputer:
        """
        Compute degradation for higher-is-better metrics such as pass rate.

        Formula: baseline score - current score.
        Example: baseline 1.0 and current 0.9 produce a drop of 0.1.
        """

        def compute(baseline: dict[str, Any], report: dict[str, Any]) -> float | None:
            base = baseline.get(baseline_key)
            current = report.get(baseline_key)
            if base is None or current is None:
                return None
            return round(float(base) - float(current), 3)

        return compute

    def _p95_increase(baseline: dict[str, Any], report: dict[str, Any]) -> float | None:
        """
        Compute the relative increase in p95 latency, where lower is better.

        Formula: (current latency - baseline latency) / baseline latency.
        Example: 57 seconds to 68 seconds is approximately a 19% increase.
        """
        base = baseline.get("p95_latency_seconds")
        current = report.get("p95_latency_seconds")
        if base is None or current is None or float(base) <= 0:
            return None
        return round((float(current) - float(base)) / float(base), 3)

    def _critical_failures_new(baseline: dict[str, Any], report: dict[str, Any]) -> int:
        """
        Compute the increase in critical failures, where lower is better.

        Formula: current critical_failures - baseline critical_failures.
        Example: a baseline of 0 and current value of 2 should block release.
        """
        return int(report.get("critical_failures", 0)) - int(baseline.get("critical_failures", 0))

    return {
        "avg_task_success_drop": _drop("avg_task_success"),
        "task_success_drop": _drop("avg_task_success"),
        "avg_groundedness_drop": _drop("avg_groundedness"),
        "groundedness_drop": _drop("avg_groundedness"),
        "pass_rate_drop": _drop("pass_rate"),
        "p95_latency_increase": _p95_increase,
        "critical_failures_new": _critical_failures_new,
        "critical_failures_delta": _critical_failures_new,
    }


def evaluate_gate(report: dict[str, Any], criteria: dict[str, str]) -> dict[str, Any]:
    """
    Run the first gate: absolute threshold checks.

    This gate considers only the current report, not the historical baseline.
    Typical rules include pass rate >= 85% and critical failures == 0.

    Return the overall result and details for every metric.
    """
    llm_skipped = report.get("llm_judged_cases", 0) == 0

    checks: dict[str, dict[str, Any]] = {}
    for key, expr in criteria.items():
        if llm_skipped and key in LLM_METRICS:
            checks[key] = {"pass": True, "skipped": True, "reason": "LLM judge skipped"}
            continue
        actual = report.get(key)
        if actual is None:
            checks[key] = {"pass": False, "reason": f"Missing metric: {key}"}
            continue
        passed = _parse_criterion(expr, actual)
        checks[key] = {"pass": passed, "actual": actual, "criteria": expr}

    all_passed = all(c.get("pass") for c in checks.values())
    return {"pass": all_passed, "checks": checks}


def evaluate_regression_gate(
    baseline: dict[str, Any],
    report: dict[str, Any],
    rules: dict[str, str],
) -> dict[str, Any]:
    """
    Run the second gate: check for significant regression against the baseline.

    The baseline is the last frozen set of acceptable results.
    Typical rules limit score drops to 0.03, latency increases to 20%, and new
    critical failures to zero.

    A result can therefore be blocked despite meeting absolute thresholds.
    """
    llm_skipped = report.get("llm_judged_cases", 0) == 0
    computers = _regression_computers()
    checks: dict[str, dict[str, Any]] = {}

    for key, expr in rules.items():
        computer = computers.get(key)
        if computer is None:
            checks[key] = {"pass": False, "reason": f"Unknown regression rule: {key}"}
            continue

        baseline_metric_key = {
            "avg_task_success_drop": "avg_task_success",
            "task_success_drop": "avg_task_success",
            "avg_groundedness_drop": "avg_groundedness",
            "groundedness_drop": "avg_groundedness",
            "pass_rate_drop": "pass_rate",
        }.get(key)

        if llm_skipped and baseline_metric_key in LLM_METRICS:
            checks[key] = {"pass": True, "skipped": True, "reason": "LLM judge skipped"}
            continue

        actual = computer(baseline, report)
        if actual is None:
            checks[key] = {
                "pass": True,
                "skipped": True,
                "reason": "Metric unavailable in baseline or report",
            }
            continue

        passed = _parse_criterion(expr, actual)
        checks[key] = {
            "pass": passed,
            "actual": actual,
            "criteria": expr,
            "baseline": baseline.get(baseline_metric_key or "p95_latency_seconds"),
            "current": report.get(baseline_metric_key or "p95_latency_seconds"),
        }
        if key in {"critical_failures_new", "critical_failures_delta"}:
            checks[key]["baseline"] = baseline.get("critical_failures")
            checks[key]["current"] = report.get("critical_failures")

    all_passed = all(c.get("pass") for c in checks.values())
    return {"pass": all_passed, "checks": checks}


def evaluate_all_gates(
    report: dict[str, Any],
    *,
    absolute_criteria: dict[str, str],
    baseline: dict[str, Any] | None = None,
    regression_rules: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Run both gates and determine whether the release is allowed.

    - Run absolute thresholds first.
    - Run regression checks when a baseline is available.
    - Both gates must pass for an overall pass.
    """
    absolute = evaluate_gate(report, absolute_criteria)
    regression: dict[str, Any] | None = None
    if baseline is not None and regression_rules:
        regression = evaluate_regression_gate(baseline, report, regression_rules)

    passed = absolute["pass"] and (regression is None or regression["pass"])
    return {"pass": passed, "absolute": absolute, "regression": regression}


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load absolute-threshold or regression-gate rules from YAML."""
    import yaml

    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _print_checks(label: str, result: dict[str, Any], *, passed: bool) -> None:
    """
    Print gate results in an operator-friendly format.

    Each item is marked as ok or FAIL and includes baseline/current values.
    """
    status = "PASS" if passed else "BLOCK"
    print(f"[gate] {status}: {label}")
    for key, check in result["checks"].items():
        if check.get("skipped"):
            print(f"  {key}: skipped ({check.get('reason')})")
            continue
        marker = "ok" if check.get("pass") else "FAIL"
        actual = check.get("actual")
        criteria = check.get("criteria")
        extra = ""
        if "baseline" in check and "current" in check:
            extra = f" (baseline={check['baseline']}, current={check['current']})"
        print(f"  [{marker}] {key}: {actual} ({criteria}){extra}")


def main() -> None:
    """
    Command-line entry point for run_eval.sh and CI.

    1. Read the current eval_report.json.
    2. Read the rules and baseline.json.
    3. Run both gates.
    4. Exit 0 to allow release or 1 to block it.
    """
    parser = argparse.ArgumentParser(description="Evaluate release gate")
    parser.add_argument(
        "report_path",
        nargs="?",
        default="eval_harness/reports/eval_report.json",
        help="Path to eval report JSON",
    )
    parser.add_argument(
        "--criteria",
        default=str(DEFAULT_ABSOLUTE_RULES),
        help="Path to absolute threshold rules YAML",
    )
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_BASELINE),
        help="Path to baseline eval report JSON for regression gate",
    )
    parser.add_argument(
        "--regression-rules",
        default=str(DEFAULT_REGRESSION_RULES),
        help="Path to regression rules YAML",
    )
    parser.add_argument(
        "--skip-regression",
        action="store_true",
        help="Run absolute gate only (skip baseline comparison)",
    )
    args = parser.parse_args()

    report_path = Path(args.report_path)
    if not report_path.exists():
        print(f"[gate] BLOCK: report not found: {report_path}")
        raise SystemExit(1)

    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)

    criteria_path = Path(args.criteria)
    absolute_criteria = _load_yaml(criteria_path) if criteria_path.exists() else {}

    baseline: dict[str, Any] | None = None
    regression_rules: dict[str, str] | None = None
    if not args.skip_regression:
        from eval_harness.baselines.resolve import (
            regression_check_rules,
            resolve_baseline_path,
        )

        rules_path = Path(args.regression_rules)
        raw_rules = _load_yaml(rules_path) if rules_path.exists() else {}
        # CLI --baseline wins only when it is an explicit non-default path that exists.
        cli_baseline = Path(args.baseline)
        explicit_cli = (
            args.baseline != str(DEFAULT_BASELINE) and cli_baseline.exists()
        )
        baseline_path = resolve_baseline_path(
            cli_path=cli_baseline if explicit_cli else None,
            regression_rules=raw_rules,
            prefer_cli=explicit_cli,
        )
        if not baseline_path.is_absolute():
            baseline_path = Path.cwd() / baseline_path

        if baseline_path.exists() and raw_rules:
            with open(baseline_path, encoding="utf-8") as f:
                baseline = json.load(f)
            regression_rules = regression_check_rules(raw_rules)
            print(f"[gate] regression baseline: {baseline_path}")
        elif baseline_path.exists():
            print(f"[gate] WARN: regression rules not found at {rules_path}; skipping regression")
        else:
            print(f"[gate] WARN: baseline not found at {baseline_path}; skipping regression")

    result = evaluate_all_gates(
        report,
        absolute_criteria=absolute_criteria,
        baseline=baseline,
        regression_rules=regression_rules,
    )

    _print_checks("absolute thresholds met", result["absolute"], passed=result["absolute"]["pass"])
    if result["regression"] is not None:
        _print_checks(
            "regression vs baseline",
            result["regression"],
            passed=result["regression"]["pass"],
        )

    # Persist for reliability dashboard + optional BigQuery export
    gate_path = report_path.parent / "gate_result.json"
    with open(gate_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"[gate] result saved to {gate_path}")
    try:
        from observability.analytics.bigquery_exporter import export_gate_result_to_bigquery

        export_gate_result_to_bigquery(result)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[gate] BigQuery export skipped/failed: {exc}")

    raise SystemExit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
