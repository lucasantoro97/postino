from __future__ import annotations

import re

from .models import EmailMeta

_DEADLINE_RE = re.compile(r"\b(due|deadline|overdue|today|tomorrow|asap|urgent)\b", re.IGNORECASE)
_MONEY_RE = re.compile(r"\b(invoice|payment|wire|bank|amount|€|\\$)\b", re.IGNORECASE)
_LEGAL_RE = re.compile(r"\b(contract|nda|legal|terms|liability|termination)\b", re.IGNORECASE)
_CANCEL_RE = re.compile(r"\b(cancel|cancellation|reschedul|postpone)\b", re.IGNORECASE)


def compute_priority(
    meta: EmailMeta,
    text: str,
    *,
    vip_senders: list[str],
) -> tuple[int, list[str]]:
    score = 0
    tags: list[str] = []

    from_addr = (meta.from_addr or "").lower()
    if any(v.lower() in from_addr for v in vip_senders):
        score += 50
        tags.append("vip")

    if _DEADLINE_RE.search(text):
        score += 25
        tags.append("deadline")
    if _MONEY_RE.search(text):
        score += 20
        tags.append("money")
    if _LEGAL_RE.search(text):
        score += 20
        tags.append("legal")
    if _CANCEL_RE.search(text):
        score += 10
        tags.append("cancel")

    subj = (meta.subject or "").lower()
    if "re:" in subj:
        score += 5
        tags.append("thread")

    return score, tags
