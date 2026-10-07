"""Skills Registry unit tests (Sprint 5.5) - ADK SKILL.md only."""

from __future__ import annotations

import pytest

from skills.loader import (
    INTENT_ALARM,
    INTENT_POLICY,
    INTENT_WORKORDER,
    SOURCE_ADK,
    canonical_skill_id,
    clear_skills_cache,
    get_skill,
    list_skill_ids,
    load_skills,
    match_intent,
    match_skill,
    skill_for_intent,
)

CORE_SKILLS = {
    "alarm-investigation",
    "policy-lookup",
    "workorder-recommendation",
}


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_skills_cache()
    yield
    clear_skills_cache()


def test_load_skills_has_three_adk_skills():
    ids = set(list_skill_ids())
    assert ids == CORE_SKILLS
    for skill in load_skills():
        assert skill.source == SOURCE_ADK
        assert skill.description.strip()
        assert skill.allowed_tools
        assert skill.instructions.strip()
        assert skill.version
        assert skill.intent in {INTENT_ALARM, INTENT_POLICY, INTENT_WORKORDER}


@pytest.mark.parametrize(
    "skill_id,intent,tools",
    [
        ("alarm-investigation", INTENT_ALARM, {"search_alarm_history", "search_similar_cases"}),
        ("policy-lookup", INTENT_POLICY, {"search_policy_doc"}),
        ("workorder-recommendation", INTENT_WORKORDER, {"recommend_work_order"}),
    ],
)
def test_adk_skill_tools_are_domain_narrow(skill_id: str, intent: str, tools: set[str]):
    skill = get_skill(skill_id)
    assert skill.intent == intent
    assert set(skill.allowed_tools) == tools
    # Do not cross domains.
    assert not (set(skill.allowed_tools) - tools)


def test_underscore_id_is_lookup_alias_only():
    assert canonical_skill_id("policy_lookup") == "policy-lookup"
    assert get_skill("policy_lookup").id == "policy-lookup"
    assert get_skill("workorder_recommendation").id == "workorder-recommendation"
    assert "policy_lookup" not in list_skill_ids()


def test_match_skill_policy_lookup():
    skill = match_skill(
        "What does HVAC-MNT-001 say about filter replacement for AHU units? Cite policy rules only."
    )
    assert skill.id == "policy-lookup"
    assert skill.intent == INTENT_POLICY
    assert skill.source == SOURCE_ADK


def test_match_skill_workorder():
    skill = match_skill("Escalate ticket WO-2026-0142 to high priority.")
    assert skill.id == "workorder-recommendation"
    assert skill.intent == INTENT_WORKORDER


def test_match_skill_alarm_default():
    skill = match_skill(
        "The HVAC alarm on Floor 3 keeps recurring. Check history and recommend priority."
    )
    assert skill.id == "alarm-investigation"
    assert skill.intent == INTENT_ALARM
    assert match_intent(
        "The HVAC alarm on Floor 3 keeps recurring. Check history and recommend priority."
    ) == INTENT_ALARM


def test_skill_for_intent_roundtrip():
    assert skill_for_intent(INTENT_POLICY).id == "policy-lookup"
    assert skill_for_intent(INTENT_WORKORDER).id == "workorder-recommendation"
    assert skill_for_intent(INTENT_ALARM).id == "alarm-investigation"


def test_get_skill_unknown_raises():
    with pytest.raises(KeyError, match="Unknown skill"):
        get_skill("not_a_real_skill")


def _write_adk_skill(root, name: str, *, intent: str = "alarm") -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    tools = {
        "alarm": "search_alarm_history",
        "policy": "search_policy_doc",
        "workorder": "recommend_work_order",
    }[intent]
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        "description: Test skill used by loader fail-fast tests.\n"
        "metadata:\n"
        "  version: \"0.0.1\"\n"
        "  legacy_router:\n"
        f"    intent: {intent}\n"
        "    match_hints: [alarm]\n"
        "  adk_additional_tools:\n"
        f" - {tools}\n"
        "---\n\n# Test\n",
        encoding="utf-8",
    )


def test_legacy_skill_yaml_fails_fast(tmp_path):
    skill_dir = tmp_path / "legacy-only"
    skill_dir.mkdir()
    (skill_dir / "skill.yaml").write_text("id: legacy-only\nintent: alarm\n", encoding="utf-8")
    # no SKILL.md -> not discovered; empty root raises FileNotFoundError
    clear_skills_cache()
    with pytest.raises(FileNotFoundError, match="No SKILL.md"):
        load_skills(str(tmp_path))


def test_skill_yaml_beside_skill_md_fails_fast(tmp_path):
    _write_adk_skill(tmp_path, "alarm-investigation")
    (tmp_path / "alarm-investigation" / "skill.yaml").write_text(
        "id: alarm-investigation\nintent: alarm\n",
        encoding="utf-8",
    )
    clear_skills_cache()
    with pytest.raises(ValueError, match="skill.yaml is no longer supported"):
        load_skills(str(tmp_path))


def test_skill_name_must_match_directory(tmp_path):
    """ADK frontmatter names must match kebab-case directory names."""
    skill_dir = tmp_path / "wrong-dir-name"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: alarm-investigation\n"
        "description: Name does not match directory.\n"
        "metadata:\n"
        "  legacy_router:\n"
        "    intent: alarm\n"
        "    match_hints: [alarm]\n"
        "  adk_additional_tools:\n"
        "    - search_alarm_history\n"
        "---\n\n# X\n",
        encoding="utf-8",
    )
    clear_skills_cache()
    with pytest.raises(ValueError, match="does not match directory name"):
        load_skills(str(tmp_path))
