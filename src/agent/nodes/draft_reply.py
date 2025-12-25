from __future__ import annotations

import logging
import re
from typing import Any

from email.utils import parseaddr

from ..deps import Deps
from ..llm_openrouter import _detect_language
from ..models import ReplyDraft
from ..rfc822 import build_reply_email

logger = logging.getLogger(__name__)


def _quote_original(text: str) -> str:
    lines = text.splitlines()
    quoted_lines = [f"> {line}" if line.strip() else ">" for line in lines]
    return "\n".join(quoted_lines)


_REPLY_SEPARATORS = [
    re.compile(r"^on .+ wrote:$", re.IGNORECASE),
    re.compile(r"^il .+ ha scritto:$", re.IGNORECASE),
    re.compile(r"^from:\s", re.IGNORECASE),
    re.compile(r"^to:\s", re.IGNORECASE),
    re.compile(r"^cc:\s", re.IGNORECASE),
    re.compile(r"^date:\s", re.IGNORECASE),
    re.compile(r"^sent:\s", re.IGNORECASE),
    re.compile(r"^inviato:\s", re.IGNORECASE),
    re.compile(r"^subject:\s", re.IGNORECASE),
    re.compile(r"^-----original message-----$", re.IGNORECASE),
    re.compile(r"^begin forwarded message:$", re.IGNORECASE),
]


def _extract_latest_text(text: str) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if any(pat.match(stripped) for pat in _REPLY_SEPARATORS):
            break
        kept.append(line)
    trimmed = "\n".join(kept).strip()
    if trimmed:
        return trimmed
    unquoted = "\n".join(line.lstrip("> ").rstrip() for line in lines if line.strip()).strip()
    return unquoted or text.strip()


def _has_meaningful_reply(body: str) -> bool:
    words = 0
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(">"):
            continue
        if any(pat.match(stripped) for pat in _REPLY_SEPARATORS):
            continue
        words += len(re.findall(r"[A-Za-zÀ-ÿ']+", stripped))
        if words >= 3:
            return True
    return False


def _fallback_reply_body(meta: Any, text: str) -> str:
    language = _detect_language(text, meta.subject or "")
    if language == "it":
        return "Grazie per la tua email.\n\nTi rispondo appena possibile.\n\nCordiali saluti,\n"
    return "Thanks for your email.\n\nI will get back to you shortly.\n\nBest regards,\n"


def _normalize_addr(value: str | None) -> str:
    _, addr = parseaddr(value or "")
    return addr.lower().strip()


def _is_addressed_to_user(meta: Any, user_email: str) -> bool:
    user_email = _normalize_addr(user_email)
    if not user_email:
        return True
    recipients = {addr for addr in (meta.to_addrs + meta.cc_addrs) if addr}
    if recipients:
        return user_email in recipients
    raw = " ".join(part for part in [meta.to_addr, meta.cc_addr] if part)
    return user_email in raw.lower()


def _compute_reply_all_cc(meta: Any, user_email: str) -> list[str]:
    user_email = _normalize_addr(user_email)
    to_addr = _normalize_addr(meta.reply_to or meta.from_addr)
    seen: set[str] = set()
    cc: list[str] = []
    for addr in meta.to_addrs + meta.cc_addrs:
        addr = addr.lower().strip()
        if not addr or addr in seen:
            continue
        if addr == user_email or addr == to_addr:
            continue
        seen.add(addr)
        cc.append(addr)
    return cc


def _format_original_context(meta: Any, text: str) -> str:
    header_lines: list[str] = []
    if meta.from_addr:
        header_lines.append(f"From: {meta.from_addr}")
    if meta.to_addr:
        header_lines.append(f"To: {meta.to_addr}")
    if meta.cc_addr:
        header_lines.append(f"Cc: {meta.cc_addr}")
    if meta.date:
        header_lines.append(f"Date: {meta.date}")
    if meta.subject:
        header_lines.append(f"Subject: {meta.subject}")
    quoted = _quote_original(text)
    intro = ""
    if meta.date and meta.from_addr:
        intro = f"On {meta.date}, {meta.from_addr} wrote:"
    elif meta.from_addr:
        intro = f"{meta.from_addr} wrote:"
    elif meta.date:
        intro = f"On {meta.date}:"
    if header_lines:
        header_block = "\n".join(header_lines)
        if intro:
            return f"{intro}\n{header_block}\n\n{quoted}\n"
        return f"Original message:\n{header_block}\n\n{quoted}\n"
    if intro:
        return f"{intro}\n{quoted}\n"
    return f"Original message:\n{quoted}\n"


def draft_reply_node(state: dict[str, Any], deps: Deps) -> dict[str, Any]:
    actions = state["actions"]
    if not actions.create_draft:
        return state
    meta = state["meta"]
    if not _is_addressed_to_user(meta, deps.settings.imap_username):
        logger.info(
            "Skipping draft for email not addressed to account",
            extra={"event": "draft_skipped_not_addressed", "email_uid": meta.uid},
        )
        return state
    try:
        flags = deps.imap.fetch_flags(meta.uid)
    except Exception:
        logger.exception(
            "Failed fetching flags",
            extra={"event": "imap_flags_failed", "email_uid": meta.uid, "email_folder": meta.folder},
        )
        flags = set()
    if "\\Answered" in flags:
        logger.info(
            "Skipping draft for answered email",
            extra={"event": "draft_skipped_answered", "email_uid": meta.uid},
        )
        return state
    if deps.settings.imap_sent_folder and meta.message_id:
        sent_folder = deps.settings.imap_sent_folder
        with deps.imap.temporary_select(sent_folder, readonly=True):
            in_reply_matches = deps.imap.uid_search_header("In-Reply-To", meta.message_id)
            ref_matches = deps.imap.uid_search_header("References", meta.message_id)
        if in_reply_matches or ref_matches:
            logger.info(
                "Skipping draft for already replied email",
                extra={"event": "draft_skipped_sent_match", "email_uid": meta.uid},
            )
            return state
    existing = deps.store.get_message_draft_uid(meta.folder, meta.uid)
    if existing:
        next_state = dict(state)
        next_state.update({"draft_uid": existing})
        return next_state

    raw_text = state["text"].strip()
    latest_text = _extract_latest_text(raw_text)
    draft = deps.llm.draft_reply(meta=meta, text=latest_text)
    if not _has_meaningful_reply(draft.body):
        draft = ReplyDraft(
            to_addr=draft.to_addr,
            cc_addrs=draft.cc_addrs,
            subject=draft.subject,
            body=_fallback_reply_body(meta, latest_text),
            in_reply_to=draft.in_reply_to,
            references=draft.references,
        )
    draft.cc_addrs = _compute_reply_all_cc(meta, deps.settings.imap_username)
    original = latest_text
    if original:
        context = _format_original_context(meta, original)
        draft.body = f"{draft.body.rstrip()}\n\n{context}"
    msg_bytes = build_reply_email(from_addr=deps.settings.imap_username, draft=draft)
    res = deps.imap.append(deps.settings.imap_drafts_folder, msg_bytes, flags=("\\Draft",))
    if not res.ok:
        raise RuntimeError(f"IMAP APPEND failed: {res.raw_response!r}")
    deps.store.set_draft_uid(meta.folder, meta.uid, res.appended_uid)
    logger.info(
        "Draft created",
        extra={"event": "draft_created", "email_uid": meta.uid, "email_folder": meta.folder},
    )
    next_state = dict(state)
    next_state.update({"draft_uid": res.appended_uid})
    return next_state
