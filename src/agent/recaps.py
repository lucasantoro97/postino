from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .state_store import RecentMessage, StateStore


@dataclass(frozen=True)
class Recap:
    subject: str
    body: str


def build_daily_recap(
    *,
    store: StateStore,
    now_local: datetime,
    lookback_hours: int,
    subject_prefix: str,
) -> Recap:
    recent = store.recent_messages(lookback_hours=lookback_hours)
    calendar_msgs = store.recent_calendar_messages(lookback_hours=lookback_hours)
    drafts = store.recent_draft_messages(lookback_hours=lookback_hours)
    counts = store.recent_category_counts(lookback_hours=lookback_hours)

    lines: list[str] = []
    lines.append(f"Daily Recap — {now_local.strftime('%Y-%m-%d')}")
    lines.append("")

    lines.append("Activity summary (last 24h):")
    if not counts:
        lines.append("- No activity.")
    else:
        for category, count in counts:
            lines.append(f"- {category}: {count}")
    lines.append("")

    lines.append("Calendar items created:")
    if not calendar_msgs:
        lines.append("- None.")
    else:
        for m in calendar_msgs[:15]:
            lines.append(_fmt_msg(m))
    lines.append("")

    lines.append("Drafts created:")
    if not drafts:
        lines.append("- None.")
    else:
        for m in drafts[:20]:
            lines.append(_fmt_msg(m))
    lines.append("")

    lines.append("Top processed items:")
    if not recent:
        lines.append("- None.")
    else:
        for m in recent[:20]:
            lines.append(_fmt_msg(m))

    subject = f"{subject_prefix} {now_local.strftime('%Y-%m-%d')}"
    return Recap(subject=subject, body="\n".join(lines).strip() + "\n")


def build_weekly_recap(
    *,
    store: StateStore,
    now_local: datetime,
    lookback_days: int,
    subject_prefix: str,
) -> Recap:
    lookback_hours = lookback_days * 24
    recent = store.recent_messages(lookback_hours=lookback_hours)
    calendar_msgs = store.recent_calendar_messages(lookback_hours=lookback_hours)
    counts = store.recent_category_counts(lookback_hours=lookback_hours)
    week_key = _week_key(now_local)

    lines: list[str] = []
    lines.append(f"Weekly Recap — {week_key}")
    lines.append("")

    lines.append("Activity summary (last 7 days):")
    if not counts:
        lines.append("- No activity.")
    else:
        for category, count in counts:
            lines.append(f"- {category}: {count}")
    lines.append("")

    lines.append("Calendar items created:")
    if not calendar_msgs:
        lines.append("- None.")
    else:
        for m in calendar_msgs[:25]:
            lines.append(_fmt_msg(m))
    lines.append("")

    lines.append("Top processed items:")
    if not recent:
        lines.append("- None.")
    else:
        for m in recent[:30]:
            lines.append(_fmt_msg(m))

    subject = f"{subject_prefix} {week_key}"
    return Recap(subject=subject, body="\n".join(lines).strip() + "\n")


def build_replied_digest(
    *,
    store: StateStore,
    now_local: datetime,
    lookback_minutes: int,
    subject_prefix: str,
) -> Recap:
    now_utc = now_local.astimezone(timezone.utc)
    since = (now_utc - timedelta(minutes=int(lookback_minutes))).isoformat()
    moves = store.replied_moves_since(since_utc_iso=since)
    lines: list[str] = []
    stamp = now_local.strftime("%Y-%m-%d %H:00")
    lines.append(f"Reply Cleanup Digest — {stamp}")
    lines.append("")
    if not moves:
        lines.append(f"No replied messages were removed from ToReply in the last {lookback_minutes} minutes.")
    else:
        lines.append(f"Moved out of ToReply (replied) in the last {lookback_minutes} minutes:")
        for m in moves[:50]:
            subj = (m.subject or "").strip().replace("\n", " ")
            from_addr = (m.from_addr or "").strip().replace("\n", " ")
            lines.append(f"- {subj} — {from_addr}")
    subject = f"{subject_prefix} {now_local.strftime('%Y-%m-%d %H:00')}"
    return Recap(subject=subject, body="\n".join(lines).strip() + "\n")


def should_run_daily(
    *,
    now_utc: datetime,
    tz: str,
    time_local_hhmm: str,
) -> tuple[bool, str]:
    tzinfo = ZoneInfo(tz)
    now_local = now_utc.astimezone(tzinfo)
    try:
        hh, mm = (int(x) for x in time_local_hhmm.split(":", 1))
    except Exception as e:
        raise ValueError("Time must be HH:MM") from e
    scheduled_local = now_local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if now_local >= scheduled_local:
        return True, now_local.strftime("%Y-%m-%d")
    return False, now_local.strftime("%Y-%m-%d")


def should_run_weekly(
    *,
    now_utc: datetime,
    tz: str,
    time_local_hhmm: str,
    day_local: str,
) -> tuple[bool, str]:
    tzinfo = ZoneInfo(tz)
    now_local = now_utc.astimezone(tzinfo)
    weekday = _parse_weekday(day_local)
    ok_day = now_local.weekday() == weekday
    ok_time, _ = should_run_daily(now_utc=now_utc, tz=tz, time_local_hhmm=time_local_hhmm)
    return ok_day and ok_time, _week_key(now_local)


def _week_key(value: datetime) -> str:
    iso_year, iso_week, _ = value.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _parse_weekday(value: str) -> int:
    lowered = value.strip().lower()
    if lowered.isdigit():
        day = int(lowered)
        if 0 <= day <= 6:
            return day
    names = {
        "mon": 0,
        "monday": 0,
        "tue": 1,
        "tuesday": 1,
        "wed": 2,
        "wednesday": 2,
        "thu": 3,
        "thursday": 3,
        "fri": 4,
        "friday": 4,
        "sat": 5,
        "saturday": 5,
        "sun": 6,
        "sunday": 6,
    }
    if lowered in names:
        return names[lowered]
    raise ValueError("WEEKLY_RECAP_DAY_LOCAL must be Mon..Sun or 0..6")


def _fmt_msg(m: RecentMessage) -> str:
    subj = (m.subject or "").strip().replace("\n", " ")
    from_addr = (m.from_addr or "").strip().replace("\n", " ")
    cat = m.category or "?"
    folder = m.filing_folder or m.folder
    uid = m.uid
    return f"- [{cat}] {subj} — {from_addr} (folder={folder}, uid={uid})"
