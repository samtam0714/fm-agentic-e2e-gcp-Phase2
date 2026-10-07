import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "mock"

GENERIC_ASSET_TERMS = {"hvac", "ahu", "floor", "building"}
ACTIVE_STATUSES = {"open", "in_progress", "dispatched", "new"}


def _required_recurring_policy(issue: dict | None) -> str | None:
    """Return the policy that must be cited for recurring alarms of this issue type."""
    if issue is None:
        return "HVAC-MNT-003"
    alarm_type = issue.get("alarm_type", "")
    if alarm_type == "filter_pressure_high":
        return "HVAC-MNT-001"
    if alarm_type in {"high_supply_air_temp"}:
        return "HVAC-MNT-003"
    return None


def _load_json(name: str) -> list:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def audit_recommendation(
    asset_id: str,
    event_count: int,
    is_recurring: bool,
    policy_ids: list[str],
    work_order_action: str,
    should_create: bool,
    cited_likely_cause: str | None = None,
    alarm_issue_id: str | None = None,
) -> dict:
    """Audit a multi-agent recommendation for groundedness and policy compliance.

    Validates evidence against mock issues/policies and checks must-not rules
    such as creating work orders without policy support.
    """
    violations: list[str] = []
    must_not_violations: list[str] = []
    checks: list[dict] = []

    issues = _load_json("issues.json")
    policies = _load_json("policies.json")
    known_policy_ids = {p["policy_id"] for p in policies}

    if not asset_id.strip():
        violations.append("asset_id is missing.")
    elif asset_id.strip().lower() in GENERIC_ASSET_TERMS:
        must_not_violations.append(
            f"Generic asset identifier '{asset_id}' used instead of exact asset ID."
        )

    issue = None
    if alarm_issue_id:
        issue = next((i for i in issues if i["issue_id"] == alarm_issue_id), None)
        if issue is None:
            violations.append(f"alarm_issue_id '{alarm_issue_id}' not found in issues.")
        else:
            checks.append({"check": "issue_found", "pass": True})
    else:
        issue = next((i for i in issues if i.get("asset_id") == asset_id), None)

    if issue:
        if issue.get("asset_id") != asset_id:
            violations.append("asset_id does not match linked issue record.")
        if event_count != issue.get("event_count"):
            violations.append(
                f"event_count {event_count} does not match issue record "
                f"({issue.get('event_count')})."
            )
        if is_recurring and issue.get("event_count", 0) < 3:
            violations.append("Marked recurring but issue event_count < 3.")
        if cited_likely_cause and issue.get("likely_cause"):
            if issue["likely_cause"].lower() not in cited_likely_cause.lower():
                violations.append(
                    f"likely_cause '{cited_likely_cause}' not grounded in issue "
                    f"likely_cause '{issue.get('likely_cause')}'."
                )
    elif asset_id.strip():
        violations.append(f"No issue record found for asset_id '{asset_id}'.")

    if not policy_ids:
        if should_create or work_order_action == "create_new":
            must_not_violations.append(
                "Work order creation recommended without citing any policy."
            )
    else:
        for pid in policy_ids:
            if pid not in known_policy_ids:
                violations.append(f"Unknown policy_id '{pid}' cited.")
        required_policy = _required_recurring_policy(issue)
        if (
            is_recurring
            and event_count >= 3
            and required_policy
            and required_policy not in policy_ids
        ):
            violations.append(
                f"Recurring alarm with 3+ events should cite policy {required_policy}."
            )

    if work_order_action in {"close_existing", "no_action"} and is_recurring and event_count >= 3:
        must_not_violations.append(
            "Dismiss recurring alarm (close/no_action) when policy requires escalation."
        )

    if should_create and work_order_action == "create_new" and event_count < 3:
        must_not_violations.append(
            "Work order creation requested without meeting recurring threshold (>= 3 events)."
        )

    if work_order_action == "create_new" and issue:
        linked = issue.get("linked_workorders") or []
        tickets = _load_json("tickets.json")
        ticket_by_id = {t["work_order_id"]: t for t in tickets}
        active_linked = [
            wo_id
            for wo_id in linked
            if ticket_by_id.get(wo_id, {}).get("status") in ACTIVE_STATUSES
        ]
        if active_linked:
            must_not_violations.append(
                "create_new recommended but issue has active linked work orders "
                f"({', '.join(active_linked)}); prefer escalate_existing."
            )

    grounded = len(violations) == 0
    passed = grounded and len(must_not_violations) == 0

    return {
        "query": {
            "asset_id": asset_id,
            "event_count": event_count,
            "is_recurring": is_recurring,
            "policy_ids": policy_ids,
            "work_order_action": work_order_action,
            "should_create": should_create,
            "cited_likely_cause": cited_likely_cause,
            "alarm_issue_id": alarm_issue_id,
        },
        "checks_run": len(checks) + 6,
        "grounded": grounded,
        "pass": passed,
        "violations": violations,
        "must_not_violations": must_not_violations,
        "summary": (
            "Audit passed: recommendation is grounded and policy-compliant."
            if passed
            else "Audit failed: see violations and must_not_violations."
        ),
    }
