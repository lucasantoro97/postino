from __future__ import annotations

from datetime import datetime, timezone

from agent.models import EventCandidate
from agent.validate_event import validate_event_candidate


def test_validate_event_happy_path() -> None:
    cand = EventCandidate(
        summary="Meet",
        start="2025-01-10 10:00",
        end="2025-01-10 11:00",
        evidence=["10am"],
    )
    res = validate_event_candidate(
        cand,
        default_tz="UTC",
        now_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    assert res.ok
    assert res.event
    assert res.event.summary == "Meet"


def test_validate_event_rejects_unparseable() -> None:
    cand = EventCandidate(summary="Meet", start="nonsense")
    res = validate_event_candidate(cand, default_tz="UTC")
    assert not res.ok
    assert res.reason == "unparseable-start"


def test_validate_event_rejects_end_before_start() -> None:
    cand = EventCandidate(summary="Meet", start="2025-01-10 10:00", end="2025-01-10 09:00")
    res = validate_event_candidate(
        cand,
        default_tz="UTC",
        now_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    assert not res.ok
    assert res.reason == "end-before-start"


def test_validate_event_handles_invalid_timezone_abbreviation() -> None:
    """Test that invalid timezone abbreviations fall back to default_tz."""
    cand = EventCandidate(
        summary="Meet",
        start="2025-01-10 10:00",
        end="2025-01-10 11:00",
        timezone="CEST",  # Invalid: abbreviation, not IANA name
    )
    res = validate_event_candidate(
        cand,
        default_tz="Europe/Rome",
        now_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    # Should succeed by falling back to Europe/Rome
    assert res.ok
    assert res.event
    assert res.event.summary == "Meet"


def test_validate_event_includes_meeting_link_from_evidence() -> None:
    cand = EventCandidate(
        summary="Sync",
        start="2025-01-10 10:00",
        end="2025-01-10 11:00",
        evidence=["Join: https://meet.google.com/abc-defg-hij"],
    )
    res = validate_event_candidate(
        cand,
        default_tz="UTC",
        now_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    assert res.ok
    assert res.event
    assert "https://meet.google.com/abc-defg-hij" in (res.event.description or "")


def test_validate_event_sets_location_from_context_text_when_missing() -> None:
    cand = EventCandidate(
        summary="Sync",
        start="2025-01-10 10:00",
        end="2025-01-10 11:00",
        location=None,
        evidence=["Meeting tomorrow"],
    )
    res = validate_event_candidate(
        cand,
        default_tz="UTC",
        context_text="Details: https://teams.microsoft.com/l/meetup-join/xyz",
        now_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    assert res.ok
    assert res.event
    assert res.event.location
    assert "teams.microsoft.com" in res.event.location
