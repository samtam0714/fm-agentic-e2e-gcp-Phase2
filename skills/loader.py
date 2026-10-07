"""Agent Skills Registry - load ADK SKILL.md and match queries (Sprint 5.5).

Only ADK-native Agent Skills are supported:
  skills/<kebab-name>/SKILL.md

Business tools activate via frontmatter.metadata.adk_additional_tools after load_skill.
Router uses match_skill(query); skill_eval uses eval_harness/skill_cases/<id>.json.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

SKILLS_DIR = Path(__file__).resolve().parent

INTENT_ALARM = "alarm"
INTENT_POLICY = "policy"
INTENT_WORKORDER = "workorder"
VALID_INTENTS = frozenset({INTENT_ALARM, INTENT_POLICY, INTENT_WORKORDER})

DEFAULT_SKILL_ID = "alarm-investigation"
SOURCE_ADK = "adk"


def canonical_skill_id(skill_id: str) -> str:
    """Treat underscore names as aliases and normalize canonical IDs to kebab-case."""
    return (skill_id or "").strip().lower().replace("_", "-")


@dataclass(frozen=True)
class Skill:
    """Local projection of an ADK Agent Skill."""

    id: str
    name: str
    description: str
    intent: str
    allowed_tools: tuple[str, ...] = ()
    match_hints: tuple[str, ...] = ()
    instructions: str = ""
    version: str = ""
    source: str = SOURCE_ADK
    path: Path | None = field(default=None, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description.strip(),
            "intent": self.intent,
            "allowed_tools": list(self.allowed_tools),
            "match_hints": list(self.match_hints),
            "version": self.version,
            "source": self.source,
        }


def _validate_intent(skill_id: str, intent: str) -> str:
    intent = (intent or "").strip().lower()
    if intent not in VALID_INTENTS:
        raise ValueError(
            f"skill {skill_id}: intent must be one of {sorted(VALID_INTENTS)}"
        )
    return intent


def _parse_adk_skill(skill_dir: Path) -> Skill:
    """Load SKILL.md with ADK validation and map it to the local Skill model."""
    from google.adk.skills import load_skill_from_dir

    adk_skill = load_skill_from_dir(skill_dir)
    metadata = adk_skill.frontmatter.metadata or {}

    router = metadata.get("legacy_router") or {}
    if not isinstance(router, dict):
        raise ValueError(f"skill {adk_skill.name}: metadata.legacy_router must be a mapping")
    if "intent" not in router:
        raise ValueError(
            f"skill {adk_skill.name}: metadata.legacy_router.intent is required "
            "while the deterministic Router is still in use"
        )

    # adk_additional_tools controls SkillToolset activation; allowed-tools is
    # only an agentskills.io specification declaration.
    allowed_tools = metadata.get("adk_additional_tools") or []
    if not isinstance(allowed_tools, list):
        raise ValueError(
            f"skill {adk_skill.name}: metadata.adk_additional_tools must be a list"
        )

    return Skill(
        id=canonical_skill_id(adk_skill.name),
        name=adk_skill.name,
        description=adk_skill.description,
        intent=_validate_intent(adk_skill.name, str(router.get("intent") or "")),
        allowed_tools=tuple(str(x) for x in allowed_tools),
        match_hints=tuple(str(x).lower() for x in (router.get("match_hints") or [])),
        instructions=adk_skill.instructions,
        version=str(metadata.get("version") or ""),
        source=SOURCE_ADK,
        path=skill_dir / "SKILL.md",
    )


def _discover_skill_dirs(root: Path | None = None) -> list[Path]:
    base = root or SKILLS_DIR
    return sorted({p.parent for p in base.glob("*/SKILL.md")})


def _load_skill_dir(skill_dir: Path) -> Skill:
    md_path = skill_dir / "SKILL.md"
    yaml_path = skill_dir / "skill.yaml"
    if yaml_path.exists():
        raise ValueError(
            f"{skill_dir}: skill.yaml is no longer supported. "
            "Migrate to SKILL.md (ADK Agent Skills) and remove skill.yaml."
        )
    if not md_path.exists():
        raise FileNotFoundError(f"{skill_dir}: missing SKILL.md")
    return _parse_adk_skill(skill_dir)


@lru_cache(maxsize=1)
def load_skills(root: str | None = None) -> tuple[Skill, ...]:
    """Load and cache skills/*/SKILL.md; tests may call clear_skills_cache()."""
    base = Path(root) if root else SKILLS_DIR
    skills: list[Skill] = []
    seen: dict[str, Path] = {}
    for skill_dir in _discover_skill_dirs(base):
        skill = _load_skill_dir(skill_dir)
        if skill.id in seen:
            raise ValueError(
                f"Duplicate skill id {skill.id!r} after normalization: "
                f"{seen[skill.id]} and {skill_dir}"
            )
        seen[skill.id] = skill_dir
        skills.append(skill)
    if not skills:
        raise FileNotFoundError(f"No SKILL.md found under {base}")
    return tuple(skills)


def clear_skills_cache() -> None:
    """Clear the load_skills cache for tests."""
    load_skills.cache_clear()


def get_skill(skill_id: str, *, root: str | None = None) -> Skill:
    """Get a skill by ID, accepting underscore aliases; raise KeyError if absent."""
    wanted = canonical_skill_id(skill_id)
    for skill in load_skills(root):
        if skill.id == wanted:
            return skill
    raise KeyError(f"Unknown skill: {skill_id}")


def list_skill_ids(*, root: str | None = None) -> list[str]:
    return [s.id for s in load_skills(root)]


def skill_for_intent(intent: str, *, root: str | None = None) -> Skill:
    """Map an intent to its single corresponding skill."""
    intent = (intent or INTENT_ALARM).strip().lower() or INTENT_ALARM
    for skill in load_skills(root):
        if skill.intent == intent:
            return skill
    return get_skill(DEFAULT_SKILL_ID, root=root)


def _hints_hit(query: str, hints: tuple[str, ...]) -> bool:
    return any(h in query for h in hints)


def match_skill(query: str, *, root: str | None = None) -> Skill:
    """Select the best skill for a query using rules shared with the Router.

    Priority:
    1. Policy-oriented without work-order/investigation language -> policy-lookup
    2. Work-order-oriented without alarm/policy language -> workorder-recommendation
    3. Everything else, including mixed investigation -> alarm-investigation
    """
    q = (query or "").strip().lower()
    skills = {s.intent: s for s in load_skills(root)}
    alarm = skills.get(INTENT_ALARM) or get_skill(DEFAULT_SKILL_ID, root=root)
    policy = skills.get(INTENT_POLICY)
    workorder = skills.get(INTENT_WORKORDER)

    if not q:
        return alarm

    has_policy = bool(policy and _hints_hit(q, policy.match_hints))
    has_wo = bool(workorder and _hints_hit(q, workorder.match_hints))
    has_alarm = bool(alarm and _hints_hit(q, alarm.match_hints))

    if has_policy and not has_wo and not any(
        k in q for k in ("investigate", "history", "recurring", "recommend")
    ):
        return policy or alarm

    if has_wo and not has_alarm and not has_policy:
        return workorder or alarm

    return alarm


def match_intent(query: str, *, root: str | None = None) -> str:
    """Map a query to an intent for Router/Planner compatibility."""
    return match_skill(query, root=root).intent
