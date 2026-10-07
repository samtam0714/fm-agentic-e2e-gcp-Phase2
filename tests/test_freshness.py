from datetime import datetime, timezone

from data.mock.freshness import (
    ANCHOR_BUFFER_DAYS,
    compute_shift,
    rebase_event_timestamps,
    rebase_issues,
)


def _issues():
    return [
        {"issue_id": "a", "latest_event": "2026-06-12T09:30:00Z", "earliest_event": "2026-05-01T10:00:00Z"},
        {"issue_id": "b", "latest_event": "2026-05-20T11:30:00Z", "earliest_event": "2026-05-20T11:30:00Z"},
    ]


def test_compute_shift_anchors_latest_near_now():
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    rebased, shift = rebase_issues(_issues(), now=now)
    latest = max(
        datetime.fromisoformat(i["latest_event"].replace("Z", "+00:00")) for i in rebased
    )
    age_days = (now - latest).days
    assert age_days == ANCHOR_BUFFER_DAYS


def test_rebase_preserves_relative_spacing():
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    original = _issues()
    rebased, _ = rebase_issues(original, now=now)

    def gap(issues):
        a = datetime.fromisoformat(issues[0]["latest_event"].replace("Z", "+00:00"))
        b = datetime.fromisoformat(issues[1]["latest_event"].replace("Z", "+00:00"))
        return a - b

    assert gap(rebased) == gap(original)


def test_rebase_event_timestamps_matches_shift():
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    shift = compute_shift(_issues(), now=now)
    events = [{"event_id": "e", "timestamp": 1780585320}]
    rebased = rebase_event_timestamps(events, shift)
    assert rebased[0]["timestamp"] == 1780585320 + shift.total_seconds()


def test_ahu_3f_02_lands_within_30_day_window():
    from agents.alarm_agent.tools import search_alarm_history

    result = search_alarm_history(asset_id="AHU-3F-02", time_range_days=30)
    assert result["match_count"] == 1
    assert result["issues"][0]["event_count"] == 1
    assert result["issues"][0]["is_recurring"] is False


def test_building_match_tolerates_customer_prefix():
    from agents.alarm_agent.tools import search_alarm_history

    result = search_alarm_history(building="DemoCorp Toronto", floor=3)
    assert result["match_count"] >= 1
    asset_ids = {i["asset_id"] for i in result["issues"]}
    assert "AHU-3F-01" in asset_ids
