import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "mock"

ACTIVE_STATUSES = {"open", "in_progress", "dispatched", "new"}


def _load_json(name: str) -> list:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def _resolve_priority(
    event_count: int,
    is_recurring: bool,
    alarm_priority: str | None,
) -> tuple[str, str]:
    """Return (priority, fm_priority) for work order recommendation."""
    if alarm_priority == "P1" or (is_recurring and event_count >= 7):
        return "high", "P1"
    if is_recurring and event_count >= 3:
        return "medium", "P2"
    return "low", "P3"


def _priority_rank(priority: str) -> int:
    return {"low": 1, "medium": 2, "high": 3}.get(priority, 0)


def recommend_work_order(
    asset_id: str,
    event_count: int = 0,
    is_recurring: bool = False,
    alarm_priority: str | None = None,
    policy_ids: list[str] | None = None,
    likely_cause: str | None = None,
) -> dict:
    """Recommend whether to create or update a work order for an asset.

    Checks existing tickets and applies recurring-alarm policy thresholds.
    Use after alarm investigation and policy search.
    """
    if not asset_id.strip():
        return {
            "query": {"asset_id": asset_id},
            "error": "asset_id must not be empty",
            "recommendation": None,
        }

    issues = _load_json("issues.json")
    issue = next((i for i in issues if i.get("asset_id") == asset_id), None)
    if issue:
        issue_count = issue.get("event_count", 0)
        if event_count == 0:
            event_count = issue_count
        elif event_count != issue_count:
            # Prefer canonical issue record over agent-supplied counts (avoids audit mismatch).
            event_count = issue_count
        if event_count >= 3:
            is_recurring = True

    tickets = _load_json("tickets.json")
    policies = _load_json("policies.json") if policy_ids else []

    active_orders = [
        t for t in tickets
        if t.get("asset_id") == asset_id and t.get("status") in ACTIVE_STATUSES
    ]

    policy_rules: list[str] = []
    if policy_ids:
        for policy in policies:
            if policy.get("policy_id") in policy_ids:
                policy_rules.extend(policy.get("rules", []))

    recommended_priority, recommended_fm_priority = _resolve_priority(
        event_count=event_count,
        is_recurring=is_recurring,
        alarm_priority=alarm_priority,
    )

    meets_policy_threshold = is_recurring and event_count >= 3

    def _rule_requires_work_order(rule: str) -> bool:
        rule_lower = rule.lower()
        if "recur" in rule_lower or "more than 3" in rule_lower:
            return meets_policy_threshold
        if "emergency" in rule_lower:
            return meets_policy_threshold
        return False

    policy_requires_wo = meets_policy_threshold or any(
        _rule_requires_work_order(rule) for rule in policy_rules
    )

    should_create = policy_requires_wo and not active_orders
    should_update = False
    update_fields: dict = {}
    action = "no_action"
    rationale_parts: list[str] = []

    if active_orders:
        existing = active_orders[0]
        action = "use_existing"
        rationale_parts.append(
            f"Active work order {existing['work_order_id']} already exists for {asset_id}."
        )
        if _priority_rank(recommended_priority) > _priority_rank(existing.get("priority", "low")):
            should_update = True
            update_fields = {
                "work_order_id": existing["work_order_id"],
                "current_priority": existing.get("priority"),
                "recommended_priority": recommended_priority,
                "recommended_fm_priority": recommended_fm_priority,
            }
            action = "escalate_existing"
            rationale_parts.append(
                f"Recommend escalating priority from {existing.get('priority')} "
                f"to {recommended_priority} due to recurring pattern"
                f"{f' and {alarm_priority} alarm severity' if alarm_priority else ''}."
            )
        else:
            rationale_parts.append(
                f"Existing priority '{existing.get('priority')}' is adequate for current policy."
            )
    elif should_create:
        action = "create_new"
        rationale_parts.append(
            f"Recurring threshold met ({event_count} events in 30 days). "
            f"Create new {recommended_priority} priority work order per policy."
        )
    else:
        action = "no_action"
        rationale_parts.append(
            "Insufficient recurrence evidence (fewer than 3 events in 30 days). "
            "Continue monitoring; do not create a work order yet."
        )

    summary = likely_cause or "Investigate recurring alarm and address root cause."
    if likely_cause and "filter" in likely_cause.lower():
        summary = f"Inspect and replace filter - likely cause: {likely_cause}."

    return {
        "query": {
            "asset_id": asset_id,
            "event_count": event_count,
            "is_recurring": is_recurring,
            "alarm_priority": alarm_priority,
            "policy_ids": policy_ids or [],
            "likely_cause": likely_cause,
        },
        "active_work_orders": active_orders,
        "policy_rules_applied": policy_rules,
        "recommendation": {
            "should_create": should_create,
            "should_update": should_update,
            "action": action,
            "priority": recommended_priority,
            "fm_priority": recommended_fm_priority,
            "summary": summary,
            "rationale": " ".join(rationale_parts),
            "update_fields": update_fields or None,
        },
    }
