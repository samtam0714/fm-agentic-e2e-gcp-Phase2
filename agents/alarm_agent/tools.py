
import json
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "mock"

ACTIVE_STATUSES = {"open", "in_progress", "dispatched", "new"}

def _load_json(name: str) -> list:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def _building_matches(building: str, issue: dict) -> bool:
    """Loosely match site/customer when users combine them, such as "DemoCorp Toronto"."""
    query = building.lower().strip()
    site = str(issue.get("site", "")).lower().strip()
    customer = str(issue.get("customer_id", "")).lower().strip()
    if not query:
        return True
    candidates = [c for c in (site, customer) if c]
    for candidate in candidates:
        if candidate == query or candidate in query or query in candidate:
            return True
    # Token matching lets "democorp toronto" match site="toronto".
    query_tokens = set(query.replace("-", " ").split())
    return any(c in query_tokens for c in candidates)

def search_alarm_history(
    floor: int | None = None,
    asset_id: str | None = None,
    building: str | None = None,
    time_range_days: int = 30,
) -> dict:
    """Search aggregated alarm issues and related events.

    Use this to investigate recurring building alarms. Query by floor,
    asset_id, or building/site name. Returns issues with event details.
    """
    from data.mock.freshness import rebase_event_timestamps, rebase_issues

    raw_issues = _load_json("issues.json")
    raw_events = _load_json("alarm_events.json")
    tickets = _load_json("tickets.json")
    ticket_by_id = {t["work_order_id"]: t for t in tickets}
    now = datetime.now(timezone.utc)

    # Rebase mock data so recent alarms remain within the 30-day window.
    issues, shift = rebase_issues(raw_issues, now=now)
    events = rebase_event_timestamps(raw_events, shift)

    matched = []
    for issue in issues:
        if floor is not None and issue.get("floor") != floor:
            continue
        if asset_id and issue.get("asset_id") != asset_id:
            continue
        if building and not _building_matches(building, issue):
            continue

        latest = datetime.fromisoformat(
            issue["latest_event"].replace("Z", "+00:00")
        )
        # Day-granularity window avoids flaky edge cases near the 30-day cutoff.
        age_days = (now - latest).days
        if age_days > time_range_days:
            continue

        issue_events = [
            e for e in events if e["event_id"] in issue.get("events", [])
        ]
        linked_workorder_details = []
        for wo_id in issue.get("linked_workorders") or []:
            ticket = ticket_by_id.get(wo_id)
            if ticket:
                status = ticket.get("status")
                linked_workorder_details.append({
                    "work_order_id": wo_id,
                    "status": status,
                    "is_active": status in ACTIVE_STATUSES,
                })
            else:
                linked_workorder_details.append({
                    "work_order_id": wo_id,
                    "status": None,
                    "is_active": False,
                })
        matched.append({
            **issue,
            "is_recurring": issue.get("event_count", 0) >= 3,
            "recent_events": issue_events,
            "linked_workorder_details": linked_workorder_details,
        })

    return {
        "query": {
            "floor": floor,
            "asset_id": asset_id,
            "building": building,
            "time_range_days": time_range_days,
        },
        "match_count": len(matched),
        "issues": matched,
    }