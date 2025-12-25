from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil import parser as date_parser

from .models import EventCandidate, ValidatedEvent


@dataclass(frozen=True)
class EventValidationResult:
    ok: bool
    event: ValidatedEvent | None = None
    reason: str | None = None


def _coerce_dt(value: str, *, tz: ZoneInfo) -> datetime:
    dt = date_parser.parse(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _resolve_timezone(tz_hint: str | None, default_tz: str) -> ZoneInfo:
    """Resolve timezone hint to ZoneInfo, falling back to default_tz on errors."""
    tz_key = tz_hint or default_tz
    try:
        return ZoneInfo(tz_key)
    except ZoneInfoNotFoundError:
        # Timezone hint is invalid (e.g., abbreviation like "CEST" instead of "Europe/Rome")
        # Fall back to default
        return ZoneInfo(default_tz)


def validate_event_candidate(
    candidate: EventCandidate,
    *,
    default_tz: str,
    now_utc: datetime | None = None,
    default_duration_minutes: int = 60,
    max_duration_minutes: int = 8 * 60,
    max_days_ahead: int = 365,
    max_days_past: int = 7,
) -> EventValidationResult:
    tz = _resolve_timezone(candidate.timezone, default_tz)
    now_utc = now_utc or datetime.now(tz=timezone.utc)

    if not candidate.summary.strip():
        return EventValidationResult(ok=False, reason="empty-summary")

    try:
        start = _coerce_dt(candidate.start, tz=tz)
    except Exception:
        return EventValidationResult(ok=False, reason="unparseable-start")

    if candidate.end:
        try:
            end = _coerce_dt(candidate.end, tz=tz)
        except Exception:
            return EventValidationResult(ok=False, reason="unparseable-end")
    else:
        minutes = candidate.duration_minutes or default_duration_minutes
        end = start + timedelta(minutes=int(minutes))

    if end <= start:
        return EventValidationResult(ok=False, reason="end-before-start")

    duration_minutes = int((end - start).total_seconds() / 60)
    if duration_minutes <= 0 or duration_minutes > max_duration_minutes:
        return EventValidationResult(ok=False, reason="duration-out-of-bounds")

    start_utc = start.astimezone(timezone.utc)
    if start_utc < (now_utc - timedelta(days=max_days_past)):
        return EventValidationResult(ok=False, reason="too-far-in-past")
    if start_utc > (now_utc + timedelta(days=max_days_ahead)):
        return EventValidationResult(ok=False, reason="too-far-in-future")

    description_lines = []
    if candidate.evidence:
        description_lines.append("Evidence:")
        description_lines.extend(f"- {e}" for e in candidate.evidence[:10])
    description = "\n".join(description_lines).strip()

    return EventValidationResult(
        ok=True,
        event=ValidatedEvent(
            summary=candidate.summary.strip(),
            start_iso=start.isoformat(),
            end_iso=end.isoformat(),
            timezone=str(tz.key),
            location=candidate.location,
            description=description,
        ),
    )
