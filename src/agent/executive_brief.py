from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from .state_store import RecentMessage, StateStore


@dataclass(frozen=True)
class ExecutiveBrief:
    subject: str
    body: str


def build_executive_brief(
    *,
    store: StateStore,
    now_local: datetime,
    lookback_hours: int,
    subject_prefix: str,
) -> ExecutiveBrief:
    recent = store.recent_messages(lookback_hours=lookback_hours)
    pending = store.pending_reply_messages()

    lines: list[str] = []
    lines.append(f"Executive Brief — {now_local.strftime('%Y-%m-%d')}")
    lines.append("")

    lines.append("Top items (last 24h):")
    if not recent:
        lines.append("- No new processed items in lookback window.")
    else:
        for m in recent[:15]:
            lines.append(_fmt_msg(m))
    lines.append("")

    lines.append("Pending replies (no draft yet):")
    if not pending:
        lines.append("- None.")
    else:
        for m in pending[:20]:
            lines.append(_fmt_msg(m))
    lines.append("")

    lines.append("Risks/alerts:")
    lines.append("- Review any items tagged with deadlines/money/legal in logs.")

    subject = f"{subject_prefix} {now_local.strftime('%Y-%m-%d')}"
    return ExecutiveBrief(subject=subject, body="\n".join(lines).strip() + "\n")


def _fmt_msg(m: RecentMessage) -> str:
    subj = (m.subject or "").strip().replace("\n", " ")
    from_addr = (m.from_addr or "").strip().replace("\n", " ")
    cat = m.category or "?"
    folder = m.filing_folder or m.folder
    uid = m.uid
    return f"- [{cat}] {subj} — {from_addr} (folder={folder}, uid={uid})"


def should_run_executive_brief(
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
        raise ValueError("EXECUTIVE_BRIEF_TIME_LOCAL must be HH:MM") from e

    scheduled_local = now_local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if now_local >= scheduled_local:
        return True, now_local.strftime("%Y-%m-%d")
    return False, now_local.strftime("%Y-%m-%d")
