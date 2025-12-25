from __future__ import annotations

from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from .models import ReplyDraft


def build_reply_email(*, from_addr: str, draft: ReplyDraft) -> bytes:
    msg = EmailMessage()
    msg["Message-ID"] = make_msgid()
    msg["Date"] = formatdate(localtime=True)
    msg["From"] = from_addr
    msg["To"] = draft.to_addr
    if draft.cc_addrs:
        msg["Cc"] = ", ".join(draft.cc_addrs)
    msg["Subject"] = draft.subject
    if draft.in_reply_to:
        msg["In-Reply-To"] = draft.in_reply_to
    if draft.references:
        msg["References"] = draft.references
    msg.set_content(draft.body.rstrip() + "\n")
    return msg.as_bytes()


def build_executive_brief_email(*, from_addr: str, to_addr: str, subject: str, body: str) -> bytes:
    msg = EmailMessage()
    msg["Message-ID"] = make_msgid()
    msg["Date"] = formatdate(localtime=True)
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body.rstrip() + "\n")
    return msg.as_bytes()
