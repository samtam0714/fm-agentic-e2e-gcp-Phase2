#!/usr/bin/env python3
"""Run golden dataset cases against root agent and produce eval report."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from eval_harness.golden_dataset.loader import load_cases
from eval_harness.golden_dataset.validate import validate_cases
from eval_harness.judges.llm_judge import judge_case_llm, merge_judge_results
from eval_harness.judges.rule_based_judge import judge_case
from eval_harness.metrics.schema import DEFAULT_CASE_CATEGORY
from eval_harness.metrics.scorer import build_report
from eval_harness.retry_policy import (
    CASE_MAX_RETRIES,
    format_rate_limit_hint,
    inter_case_delay_seconds,
    is_rate_limit_error,
    is_retryable_eval_error,
    note_rate_limit,
    pre_judge_delay_seconds,
    retry_wait_seconds,
    seconds_until_quota_cooldown,
)
from eval_harness.runner import run_case

REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"


async def _wait_for_quota_cooldown(case_id: str) -> None:
    """Apply extra delay before the next API call after a recent 429."""
    remaining = seconds_until_quota_cooldown()
    if remaining > 0:
        print(
            f"[eval] Quota cooldown for {case_id}; waiting {remaining:.0f}s..."
        )
        await asyncio.sleep(remaining)


async def _run_case_with_retry(case: dict, *, case_id: str) -> object:
    """Run one case and automatically retry rate-limit or transient network errors.

    Pass the complete case so fault injection can read golden-case configuration.
    """
    query = case["input"]
    last_error: Exception | None = None
    for attempt in range(1, CASE_MAX_RETRIES + 1):
        await _wait_for_quota_cooldown(case_id)
        try:
            return await run_case(query, golden_case=case)
        except Exception as exc:
            last_error = exc
            if not is_retryable_eval_error(exc):
                raise
            rate_limited = is_rate_limit_error(exc)
            if rate_limited:
                note_rate_limit()
                print(format_rate_limit_hint(case_id))
            wait_seconds = retry_wait_seconds(attempt, rate_limited=rate_limited)
            kind = "rate limit" if rate_limited else "transient"
            print(
                f"[eval] {kind} error (attempt {attempt}/{CASE_MAX_RETRIES}): "
                f"{type(exc).__name__}; retrying in {wait_seconds:.0f}s..."
            )
            await asyncio.sleep(wait_seconds)
    raise last_error  # type: ignore[misc]


async def run_eval(
    dataset: str = "alarm_cases",
    *,
    case_id: str | None = None,
    cases: list[dict] | None = None,
    report_filename: str = "eval_report.json",
    verbose: bool = True,
    use_llm_judge: bool = True,
) -> dict:
    """Run evaluation from a dataset name or explicit cases for skill evaluation."""
    if cases is not None:
        selected = list(cases)
    else:
        selected = load_cases(dataset)
        if case_id:
            selected = [c for c in selected if c.get("case_id") == case_id]
            if not selected:
                raise ValueError(f"Case not found in {dataset}: {case_id}")

    schema_errors = validate_cases(selected)
    if schema_errors:
        raise ValueError("Invalid golden dataset:\n" + "\n".join(schema_errors))

    results = []

    for case in selected:
        case_id = case.get("case_id", "unknown")
        category = case.get("case_category", DEFAULT_CASE_CATEGORY)
        if verbose:
            print(f"\n[eval] Running case: {case_id} [{category}]")
            print(f"[eval] Input: {case['input'][:80]}...")

        trace = await _run_case_with_retry(case, case_id=case_id)
        rule_result = judge_case(case, trace)

        if use_llm_judge:
            judge_delay = pre_judge_delay_seconds()
            if judge_delay > 0:
                print(
                    f"[eval] Pre-judge cooldown for {case_id}; "
                    f"waiting {judge_delay:.0f}s..."
                )
                await asyncio.sleep(judge_delay)
            llm_result = judge_case_llm(case, trace)
            result = merge_judge_results(rule_result, llm_result)
        else:
            result = {
                **rule_result,
                "rule_pass": rule_result.get("pass", False),
                "llm_judge_skipped": True,
            }

        result["case_category"] = case.get("case_category", DEFAULT_CASE_CATEGORY)
        result["trace_id"] = trace.trace_id
        result["trace_path"] = trace.trace_path
        results.append(result)

        if case != selected[-1]:
            case_delay = inter_case_delay_seconds()
            if case_delay > 0:
                print(f"[eval] Inter-case delay after {case_id}: {case_delay:.0f}s...")
            await asyncio.sleep(case_delay)

        if verbose:
            status = "PASS" if result["pass"] else "FAIL"
            print(f"[eval] {case_id}: {status}")
            print(f"       tools={result['actual_tools']}")
            print(f"       agents={result['actual_agents']}")
            if trace.trace_path:
                print(f"       trace={trace.trace_path}")
            if trace.session_path:
                print(f"       session={trace.session_path}")
                similar_count = len(trace.session_snapshot.get("similar_cases", []))
                print(f"       similar_cases={similar_count}")
            if use_llm_judge:
                print(
                    f"       llm: task_success={result.get('task_success')} "
                    f"groundedness={result.get('groundedness')} "
                    f"llm_pass={result.get('llm_pass')}"
                )
                if result.get("llm_reason"):
                    print(f"       llm_reason={result['llm_reason'][:120]}")
            if not result["pass"]:
                if result.get("rule_pass") is False:
                    print("       rule_fail=true")
                if use_llm_judge and result.get("llm_pass") is False:
                    print("       llm_fail=true")
                if result["missing_tools"]:
                    print(f"       missing_tools={result['missing_tools']}")
                if result["missing_agents"]:
                    print(f"       missing_agents={result['missing_agents']}")
                if result["missing_keywords"]:
                    print(f"       missing_keywords={result['missing_keywords']}")
                if result["must_not_violations"]:
                    print(f"       must_not_violations={result['must_not_violations']}")

    report = build_report(results)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / report_filename
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    # Sprint 4: Optional BigQuery export; failures do not block evaluation.
    try:
        from observability.analytics.bigquery_exporter import export_eval_report_to_bigquery

        export_eval_report_to_bigquery(report)
    except Exception as exc:  # pragma: no cover - defensive
        if verbose:
            print(f"[eval] BigQuery export skipped/failed: {exc}")

    if verbose:
        print(f"\n[eval] Report saved to {report_path}")
        print(
            f"[eval] Summary: {report['pass_count']}/{report['case_count']} passed "
            f"(pass_rate={report['pass_rate']})"
        )
        if report.get("p95_latency_seconds") is not None:
            print(
                f"[eval] Latency: p50={report['p50_latency_seconds']}s "
                f"p95={report['p95_latency_seconds']}s"
            )
        if report.get("case_category_breakdown"):
            print(f"[eval] Categories: {report['case_category_breakdown']}")
        if use_llm_judge:
            print(
                f"[eval] LLM judge: avg_task_success={report['avg_task_success']} "
                f"avg_groundedness={report['avg_groundedness']}"
            )

    return report


def _print_failure_summary(report: dict) -> None:
    """Print failed case IDs even in quiet mode so CI logs remain actionable."""
    failed = [c for c in report.get("cases", []) if not c.get("pass")]
    if not failed:
        return
    print(
        f"\n[eval] FAILED {report.get('fail_count')}/{report.get('case_count')} "
        f"case(s) (pass_rate={report.get('pass_rate')}):"
    )
    for case in failed:
        reasons = []
        if case.get("rule_pass") is False:
            reasons.append("rule_fail")
        if case.get("llm_pass") is False:
            reasons.append("llm_fail")
        if case.get("missing_tools"):
            reasons.append(f"missing_tools={case['missing_tools']}")
        if case.get("missing_agents"):
            reasons.append(f"missing_agents={case['missing_agents']}")
        if case.get("missing_keywords"):
            reasons.append(f"missing_keywords={case['missing_keywords']}")
        if case.get("must_not_violations"):
            reasons.append(f"must_not_violations={case['must_not_violations']}")
        if case.get("llm_reason"):
            reasons.append(f"llm_reason={str(case['llm_reason'])[:120]}")
        print(f"  - {case.get('case_id')}: {', '.join(reasons) or 'unknown'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run agent eval harness")
    parser.add_argument(
        "--dataset",
        default="alarm_cases",
        help="Dataset name without .json, or 'all' for alarm+safety+rag (default: alarm_cases)",
    )
    parser.add_argument(
        "--case-id",
        default=None,
        help="Run a single golden case by case_id (e.g. alarm_001)",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress per-case output")
    parser.add_argument(
        "--skip-llm-judge",
        action="store_true",
        help="Skip LLM judge (rule-based eval only)",
    )
    args = parser.parse_args()

    report = asyncio.run(
        run_eval(
            dataset=args.dataset,
            case_id=args.case_id,
            verbose=not args.quiet,
            use_llm_judge=not args.skip_llm_judge,
        )
    )
    _print_failure_summary(report)
    raise SystemExit(0 if report["fail_count"] == 0 else 1)


if __name__ == "__main__":
    main()
