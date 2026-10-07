"""Dynamically rebase absolute dates in mock alarm data near the current time.

Dates in issues.json and alarm_events.json are fixed near June 2026. As time
passes, search_alarm_history's 30-day filter would exclude formerly recent
events and cause evaluation cases to receive empty data.

At load time, use the latest event as an anchor and shift all events so it falls
ANCHOR_BUFFER_DAYS before today. Relative intervals and recurring/single-event
semantics remain unchanged.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

# Anchor the latest alarm a few days before today to keep it within 30 days.
ANCHOR_BUFFER_DAYS = 3

_ISO_DATE_FIELDS = ("latest_event", "earliest_event", "last_updated")


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _to_iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _max_latest_event(issues: list[dict[str, Any]]) -> datetime | None:
    latest: datetime | None = None
    for issue in issues:
        parsed = _parse_iso(issue.get("latest_event", ""))
        if parsed and (latest is None or parsed > latest):
            latest = parsed
    return latest


def compute_shift(issues: list[dict[str, Any]], *, now: datetime | None = None) -> timedelta:
    """Calculate the offset that places the latest issue at the target date."""
    now = now or datetime.now(timezone.utc)
    anchor = _max_latest_event(issues)
    if anchor is None:
        return timedelta(0)
    target = now - timedelta(days=ANCHOR_BUFFER_DAYS)
    return target - anchor


def rebase_issues(
    issues: list[dict[str, Any]], *, now: datetime | None = None
) -> tuple[list[dict[str, Any]], timedelta]:
    """Return shifted issue copies and the offset used to synchronize events."""
    shift = compute_shift(issues, now=now)
    if shift == timedelta(0):
        return [dict(issue) for issue in issues], shift

    rebased: list[dict[str, Any]] = []
    for issue in issues:
        new_issue = dict(issue)
        for field in _ISO_DATE_FIELDS:
            parsed = _parse_iso(issue.get(field, ""))
            if parsed:
                new_issue[field] = _to_iso_z(parsed + shift)
        timeline = issue.get("timeline")
        if isinstance(timeline, list):
            new_timeline = []
            for entry in timeline:
                new_entry = dict(entry)
                parsed = _parse_iso(entry.get("at", ""))
                if parsed:
                    new_entry["at"] = _to_iso_z(parsed + shift)
                new_timeline.append(new_entry)
            new_issue["timeline"] = new_timeline
        rebased.append(new_issue)
    return rebased, shift


def rebase_event_timestamps(
    events: list[dict[str, Any]], shift: timedelta
) -> list[dict[str, Any]]:
    """Shift event Unix timestamps to remain aligned with issue dates."""
    if shift == timedelta(0):
        return [dict(event) for event in events]
    shift_seconds = shift.total_seconds()
    rebased = []
    for event in events:
        new_event = dict(event)
        ts = event.get("timestamp")
        if isinstance(ts, (int, float)):
            new_event["timestamp"] = ts + shift_seconds
        rebased.append(new_event)
    return rebased
