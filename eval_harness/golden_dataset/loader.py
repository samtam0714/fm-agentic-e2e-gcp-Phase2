"""Load the golden dataset used for evaluation.

Four JSON files contain 30 cases total (all are merged for dataset=all):
  - alarm_cases.json   10 cases  Normal alarm escalation/create/monitor flows
  - safety_cases.json   5 cases  Refusal of unsafe user instructions
  - rag_cases.json      5 cases  Policy retrieval, similar cases, and grounding
  - failure_cases.json 10 cases  Recovery from bad input, tool failure, and timeout

Optional (excluded from dataset=all to preserve the 30-case regression baseline):
  - a2a_failure_cases.json  3 cases  Mini A2A timeout/unavailable/invalid (Sprint 7)

Supported EVAL_DATASET values:
  alarm_cases | safety_cases | rag_cases | failure_cases | a2a_failure_cases | all
"""

from __future__ import annotations

import json
from pathlib import Path

GOLDEN_DIR = Path(__file__).resolve().parent

# Merge order; add new default datasets here.
ALL_DATASETS = ("alarm_cases", "safety_cases", "rag_cases", "failure_cases")
# Stretch / opt-in datasets (load individually; not merged into "all")
OPTIONAL_DATASETS = ("a2a_failure_cases",)


def _load_file(name: str) -> list[dict]:
    path = GOLDEN_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Golden dataset not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array of cases")
    return data


def load_cases(dataset: str) -> list[dict]:
    """Load one dataset, or merge all 30 cases when dataset='all'."""
    if dataset == "all":
        merged: list[dict] = []
        for name in ALL_DATASETS:
            merged.extend(_load_file(name))
        return merged

    name = dataset.removesuffix(".json")
    return _load_file(name)
