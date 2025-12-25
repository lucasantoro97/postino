from __future__ import annotations

from email.message import EmailMessage

from agent.email_parse import parse_email


def test_parse_email_prefers_plain_text() -> None:
    msg = EmailMessage()
    msg["From"] = "a@example.com"
    msg["To"] = "b@example.com"
    msg["Cc"] = "c@example.com"
    msg["Subject"] = "Hello"
    msg.set_content("plain body")
    msg.add_alternative("<p>html body</p>", subtype="html")

    meta, text, fingerprint = parse_email(msg.as_bytes(), folder="INBOX", uid=123)
    assert meta.uid == 123
    assert meta.to_addrs == ["b@example.com"]
    assert meta.cc_addrs == ["c@example.com"]
    assert "plain body" in text
    assert fingerprint


def test_parse_email_html_only() -> None:
    msg = EmailMessage()
    msg["From"] = "a@example.com"
    msg["To"] = "b@example.com"
    msg["Subject"] = "HTML"
    msg.add_alternative("<div>Line1<br/>Line2</div>", subtype="html")

    _, text, _ = parse_email(msg.as_bytes(), folder="INBOX", uid=1)
    assert "Line1" in text
    assert "Line2" in text


def test_parse_email_lists_attachments() -> None:
    msg = EmailMessage()
    msg["From"] = "a@example.com"
    msg["To"] = "b@example.com"
    msg["Subject"] = "Attachment"
    msg.set_content("see attached")
    msg.add_attachment(b"data", maintype="application", subtype="octet-stream", filename="file.bin")

    _, text, _ = parse_email(msg.as_bytes(), folder="INBOX", uid=2)
    assert "[Attachments]" in text
    assert "file.bin" in text
