"""Resolve versioned milestone baselines for the regression gate (Sprint 1 / 2.1.5).

Milestone files live under eval_harness/baselines/*.json. Regression rules may
point at the active one via ``baseline_path``. CI still keeps
``reports/baseline.json`` as a sync copy of the active milestone for
backward-compatible upload / smoke checks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

BASELINES_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASELINES_DIR.parents[1]
REPORTS_BASELINE = BASELINES_DIR.parent / "reports" / "baseline.json"

# Newest last - used when rules omit baseline_path.
MILESTONE_ORDER = (
    "v1-thin-slice",
    "phase2-mcp",
    "phase2-planner",
    "phase2-adk-skills",
    "phase2-retrieval",
)

# Keys in regression_rules.yaml that are config, not drop/increase checks.
CONFIG_KEYS = frozenset({"baseline_path", "active_milestone"})


def milestone_path(name: str) -> Path:
    return BASELINES_DIR / f"{name}.json"


def latest_milestone_path() -> Path | None:
    """Return the newest existing milestone file, or None."""
    for name in reversed(MILESTONE_ORDER):
        path = milestone_path(name)
        if path.exists():
            return path
    # Any other *.json under baselines/ (excluding helpers)
    candidates = sorted(
        p for p in BASELINES_DIR.glob("*.json") if p.is_file()
    )
    return candidates[-1] if candidates else None


def resolve_baseline_path(
    *,
    cli_path: str | Path | None = None,
    regression_rules: dict[str, Any] | None = None,
    prefer_cli: bool = True,
) -> Path:
    """Pick which baseline JSON the regression gate should load.

    Priority:
    1. Explicit CLI ``--baseline`` when it differs from the legacy default
       and the file exists (prefer_cli=True and path was user-supplied).
    2. ``baseline_path`` or ``active_milestone`` in regression_rules.yaml
    3. Latest milestone under eval_harness/baselines/
    4. Legacy reports/baseline.json
    """
    rules = regression_rules or {}

    if prefer_cli and cli_path is not None:
        path = Path(cli_path)
        if not path.is_absolute():
            path = (REPO_ROOT / path).resolve()
        # Only treat as explicit override when it exists; otherwise fall through.
        if path.exists() and path.resolve() != REPORTS_BASELINE.resolve():
            return path

    configured = rules.get("baseline_path")
    if configured:
        path = Path(str(configured))
        if not path.is_absolute():
            path = (REPO_ROOT / path).resolve()
        return path

    milestone = rules.get("active_milestone")
    if milestone:
        return milestone_path(str(milestone))

    latest = latest_milestone_path()
    if latest is not None:
        return latest

    if cli_path is not None:
        path = Path(cli_path)
        if not path.is_absolute():
            path = (REPO_ROOT / path).resolve()
        return path

    return REPORTS_BASELINE


def regression_check_rules(rules: dict[str, Any]) -> dict[str, str]:
    """Strip config keys; keep only drop/increase criterion strings."""
    return {
        k: str(v)
        for k, v in rules.items()
        if k not in CONFIG_KEYS and isinstance(v, str)
    }
