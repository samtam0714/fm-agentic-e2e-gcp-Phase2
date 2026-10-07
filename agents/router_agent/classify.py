"""Deterministic intent classification - delegates to Skills Registry (Sprint 5.5).

Maps free-text queries to one of: alarm | policy | workorder.
Matching hints live in skills/*/SKILL.md (metadata.legacy_router.match_hints).
This module keeps the old API (classify_intent / INTENT_*) so Planner and tests stay stable.
"""

from __future__ import annotations

from skills.loader import (
    INTENT_ALARM,
    INTENT_POLICY,
    INTENT_WORKORDER,
    VALID_INTENTS,
    match_intent,
)

__all__ = [
    "INTENT_ALARM",
    "INTENT_POLICY",
    "INTENT_WORKORDER",
    "VALID_INTENTS",
    "classify_intent",
]


def classify_intent(query: str) -> str:
    """Return alarm | policy | workorder for a user query (via skill match)."""
    return match_intent(query)
