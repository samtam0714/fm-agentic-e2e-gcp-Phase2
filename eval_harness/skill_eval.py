#!/usr/bin/env python3
"""Run skill-level evaluations from skill_cases/<id>.json (Sprint 5.5).

Usage:
  uv run python -m eval_harness.skill_eval --skill alarm-investigation --skip-llm-judge
  uv run python -m eval_harness.skill_eval --skill all --skip-llm-judge
  uv run skill-eval --list
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from eval_harness.golden_dataset.loader import load_cases
from eval_harness.runners.run_agent_eval import _print_failure_summary, run_eval
from skills.loader import (
    canonical_skill_id,
    get_skill,
    list_skill_ids,
    load_skills,
)

REPORTS_DIR = Path(__file__).resolve().parent / "reports"
SKILL_CASES_DIR = Path(__file__).resolve().parent / "skill_cases"


def _skill_case_ids(skill: Any) -> list[str]:
    """Load case IDs only from external skill_cases/<id>.json files."""
    case_file = SKILL_CASES_DIR / f"{skill.id}.json"
    if not case_file.exists():
        raise ValueError(
            f"skill {skill.id}: missing {case_file}. "
            "Add a JSON file with a case_ids list."
        )
    with open(case_file, encoding="utf-8") as f:
        payload = json.load(f)
    case_ids = payload.get("case_ids")
    if not case_ids:
        raise ValueError(f"{case_file} has no case_ids")
    return [str(c) for c in case_ids]


def resolve_skill_cases(skill_id: str) -> tuple[Any, list[dict]]:
    """Load a skill and resolve its bound IDs to golden cases."""
    skill = get_skill(skill_id)
    case_ids = _skill_case_ids(skill)
    by_id = {c["case_id"]: c for c in load_cases("all")}
    missing = [cid for cid in case_ids if cid not in by_id]
    if missing:
        raise ValueError(
            f"skill {skill_id}: eval cases not found in golden dataset: {missing}"
        )
    cases = [by_id[cid] for cid in case_ids]
    return skill, cases


async def run_skill_eval(
    skill_id: str,
    *,
    verbose: bool = True,
    use_llm_judge: bool = True,
) -> dict:
    """Evaluate one skill and write skill_<id>_report.json."""
    skill, cases = resolve_skill_cases(skill_id)
    if verbose:
        print(f"\n[skill-eval] skill={skill.id} ({skill.name})")
        print(f"[skill-eval] intent={skill.intent}")
        print(f"[skill-eval] allowed_tools={list(skill.allowed_tools)}")
        print(f"[skill-eval] cases={[c['case_id'] for c in cases]}")

    report = await run_eval(
        cases=cases,
        report_filename=f"skill_{skill.id}_report.json",
        verbose=verbose,
        use_llm_judge=use_llm_judge,
    )
    report["skill_id"] = skill.id
    report["skill_name"] = skill.name
    report["skill_intent"] = skill.intent
    report["skill_version"] = skill.version
    report["skill_source"] = skill.source

    # Overwrite with current results and skill metadata.
    out = REPORTS_DIR / f"skill_{skill.id}_report.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    if verbose:
        print(f"[skill-eval] Report saved to {out}")
    return report


async def run_all_skill_evals(
    *,
    verbose: bool = True,
    use_llm_judge: bool = True,
) -> dict[str, dict]:
    """Evaluate all skills and write skill_eval_summary.json."""
    summary: dict[str, dict] = {}
    for skill in load_skills():
        report = await run_skill_eval(
            skill.id,
            verbose=verbose,
            use_llm_judge=use_llm_judge,
        )
        summary[skill.id] = {
            "pass_rate": report.get("pass_rate"),
            "pass_count": report.get("pass_count"),
            "case_count": report.get("case_count"),
            "fail_count": report.get("fail_count"),
        }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = REPORTS_DIR / "skill_eval_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    if verbose:
        print(f"\n[skill-eval] Summary saved to {summary_path}")
        print(f"[skill-eval] {json.dumps(summary, indent=2)}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run skill-level eval harness")
    parser.add_argument(
        "--skill",
        default="all",
        help="Skill id (e.g. alarm-investigation) or 'all' (default: all)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List registered skills and exit",
    )
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--skip-llm-judge",
        action="store_true",
        help="Rule-based judge only (faster, no Vertex judge calls)",
    )
    args = parser.parse_args()

    if args.list:
        for skill in load_skills():
            print(
                f"{skill.id}\tsource={skill.source}\tintent={skill.intent}\t"
                f"cases={_skill_case_ids(skill)}\ttools={list(skill.allowed_tools)}"
            )
        raise SystemExit(0)

    skill_arg = canonical_skill_id(args.skill)
    if skill_arg == "all":
        summary = asyncio.run(
            run_all_skill_evals(
                verbose=not args.quiet,
                use_llm_judge=not args.skip_llm_judge,
            )
        )
        failed = [sid for sid, s in summary.items() if (s.get("fail_count") or 0) > 0]
        raise SystemExit(0 if not failed else 1)

    if skill_arg not in list_skill_ids():
        raise SystemExit(
            f"Unknown skill {skill_arg!r}. Known: {', '.join(list_skill_ids())}"
        )

    report = asyncio.run(
        run_skill_eval(
            skill_arg,
            verbose=not args.quiet,
            use_llm_judge=not args.skip_llm_judge,
        )
    )
    _print_failure_summary(report)
    raise SystemExit(0 if report["fail_count"] == 0 else 1)


if __name__ == "__main__":
    main()
