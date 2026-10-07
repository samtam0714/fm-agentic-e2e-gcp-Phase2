"""ADK Agent Skills API compatibility smoke tests (Sprint 5.5 / 2.5.5).

The alarm skill uses the native ADK Agent Skills contract and depends on these
API shapes. This suite should fail clearly if an ADK upgrade changes them.
"""

from __future__ import annotations

import inspect

import pytest


def test_skill_toolset_feature_enabled():
    from google.adk.features import FeatureName, is_feature_enabled

    assert is_feature_enabled(FeatureName.SKILL_TOOLSET)


def test_skills_api_importable():
    from google.adk.skills import Skill, load_skill_from_dir
    from google.adk.tools.skill_toolset import SkillToolset

    assert callable(load_skill_from_dir)
    assert {"frontmatter", "instructions", "resources"} <= set(Skill.model_fields)
    assert issubclass(SkillToolset, object)


def test_skill_toolset_accepts_skills_and_additional_tools():
    from google.adk.tools.skill_toolset import SkillToolset

    params = inspect.signature(SkillToolset.__init__).parameters
    assert "skills" in params
    assert "additional_tools" in params


def test_frontmatter_supports_metadata_and_allowed_tools():
    from google.adk.skills import Frontmatter

    fields = Frontmatter.model_fields
    assert "metadata" in fields
    assert "allowed_tools" in fields
    # Version has no first-class field, so the loader reads it from metadata.
    assert "version" not in fields


def test_frontmatter_rejects_non_kebab_name():
    """Directory names must be kebab-case for load_skill_from_dir."""
    from google.adk.skills import Frontmatter

    with pytest.raises(ValueError):
        Frontmatter(name="alarm_investigation", description="x")


def test_load_skill_tool_exposes_instructions_and_activation():
    """load_skill returns instructions and records activation in state."""
    from google.adk.tools import skill_toolset

    source = inspect.getsource(skill_toolset.LoadSkillTool.run_async)
    assert "_adk_activated_skill_" in source
    assert "instructions" in source


def test_additional_tools_resolved_from_metadata_key():
    """Business tools activate through metadata.adk_additional_tools."""
    from google.adk.tools import skill_toolset

    source = inspect.getsource(
        skill_toolset.SkillToolset._resolve_additional_tools_from_state
    )
    assert "adk_additional_tools" in source
