from __future__ import annotations

import hashlib
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import getaddresses
import re

from bs4 import BeautifulSoup

from .models import EmailMeta

_MSG_ID_RE = re.compile(r"<[^>]+>")


def _decode_part(part: Message) -> str:
    payload_raw = part.get_payload(decode=True)
    payload = payload_raw if isinstance(payload_raw, (bytes, bytearray)) else b""
    charset = part.get_content_charset() or "utf-8"
    try:
        return bytes(payload).decode(charset, errors="replace")
    except LookupError:
        return bytes(payload).decode("utf-8", errors="replace")


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text("\n", strip=True)


def _parse_message_ids(header_value: str | None) -> list[str]:
    if not header_value:
        return []
    ids = _MSG_ID_RE.findall(header_value)
    if ids:
        return ids
    parts = [p.strip() for p in header_value.split() if p.strip()]
    return parts


def _extract_addresses(header_value: str | None) -> list[str]:
    if not header_value:
        return []
    addresses = []
    for _, addr in getaddresses([header_value]):
        addr = addr.strip()
        if addr:
            addresses.append(addr.lower())
    return addresses


def parse_email(raw: bytes, *, folder: str, uid: int) -> tuple[EmailMeta, str, str]:
    msg = BytesParser(policy=policy.default).parsebytes(raw)

    message_id = msg.get("Message-ID")
    in_reply_to = msg.get("In-Reply-To")
    references = _parse_message_ids(msg.get("References"))
    from_addr = msg.get("From")
    to_addr = msg.get("To")
    cc_addr = msg.get("Cc")
    reply_to = msg.get("Reply-To")
    subject = msg.get("Subject")
    date = msg.get("Date")

    plain_parts: list[str] = []
    html_parts: list[str] = []
    attachment_names: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = (part.get("Content-Disposition") or "").lower()
            if disposition.startswith("attachment"):
                filename = part.get_filename()
                if filename:
                    attachment_names.append(filename)
                continue
            if content_type == "text/plain":
                plain_parts.append(_decode_part(part))
            elif content_type == "text/html":
                html_parts.append(_decode_part(part))
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            plain_parts.append(_decode_part(msg))
        elif content_type == "text/html":
            html_parts.append(_decode_part(msg))

    text = "\n\n".join(p.strip() for p in plain_parts if p and p.strip())
    if not text and html_parts:
        text = "\n\n".join(_html_to_text(h) for h in html_parts if h and h.strip())

    if attachment_names:
        text = f"{text}\n\n[Attachments]\n" + "\n".join(f"- {n}" for n in attachment_names)

    fingerprint_source = "|".join(
        [
            message_id or "",
            (subject or "")[:200],
            date or "",
            (from_addr or "")[:200],
        ]
    ).encode("utf-8", errors="ignore")
    fingerprint = hashlib.sha256(fingerprint_source).hexdigest()

    meta = EmailMeta(
        folder=folder,
        uid=uid,
        message_id=message_id,
        in_reply_to=in_reply_to,
        references=references,
        from_addr=from_addr,
        to_addr=to_addr,
        cc_addr=cc_addr,
        to_addrs=_extract_addresses(to_addr),
        cc_addrs=_extract_addresses(cc_addr),
        reply_to=reply_to,
        subject=subject,
        date=date,
    )
    return meta, text, fingerprint
