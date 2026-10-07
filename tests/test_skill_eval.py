"""Skill-level eval harness tests (Sprint 5.5) - external skill_cases only."""

from __future__ import annotations

import json

import pytest

from eval_harness.skill_eval import SKILL_CASES_DIR, resolve_skill_cases
from skills.loader import list_skill_ids


@pytest.mark.parametrize(
    "skill_id",
    ["alarm-investigation", "policy-lookup", "workorder-recommendation"],
)
def test_skill_cases_come_from_external_file(skill_id: str):
    case_file = SKILL_CASES_DIR / f"{skill_id}.json"
    expected = json.loads(case_file.read_text(encoding="utf-8"))["case_ids"]

    skill, cases = resolve_skill_cases(skill_id)
    assert skill.id == skill_id
    assert skill.source == "adk"
    assert [c["case_id"] for c in cases] == expected
    assert all("input" in c for c in cases)


def test_underscore_alias_resolves_same_cases():
    _, from_alias = resolve_skill_cases("policy_lookup")
    _, from_canonical = resolve_skill_cases("policy-lookup")
    assert [c["case_id"] for c in from_alias] == [
        c["case_id"] for c in from_canonical
    ]


@pytest.mark.parametrize("skill_id", list_skill_ids())
def test_every_skill_eval_cases_resolve(skill_id: str):
    _, cases = resolve_skill_cases(skill_id)
    assert cases
