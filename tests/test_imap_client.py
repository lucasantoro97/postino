from __future__ import annotations

from datetime import date

import agent.imap_client as imap_client


class FakeImap:
    def __init__(
        self,
        *,
        capabilities: set[bytes],
        delimiter: str = "/",
        search_data: bytes = b"",
        fetch_flags_data: bytes = b"1 (FLAGS (\\Seen))",
    ) -> None:
        self.capabilities = capabilities
        self.delimiter = delimiter
        self.uid_calls: list[tuple] = []
        self.append_calls: list[tuple] = []
        self.created: list[str] = []
        self._mailboxes = {"INBOX"}
        self.search_data = search_data
        self.fetch_flags_data = fetch_flags_data

    def login(self, username: str, password: str) -> tuple[str, list[bytes]]:
        return ("OK", [b""])

    def logout(self) -> tuple[str, list[bytes]]:
        return ("OK", [b""])

    def list(self) -> tuple[str, list[bytes]]:
        lines = [
            f'(\\HasNoChildren) "{self.delimiter}" "{m}"'.encode() for m in sorted(self._mailboxes)
        ]
        return ("OK", lines)

    def create(self, mailbox: str) -> tuple[str, list[bytes]]:
        self.created.append(mailbox)
        self._mailboxes.add(mailbox)
        return ("OK", [b""])

    def select(self, mailbox: str, readonly: bool = False) -> tuple[str, list[bytes]]:  # noqa: ARG002
        if mailbox not in self._mailboxes:
            return ("NO", [b"missing"])
        return ("OK", [b"1"])

    def uid(self, command: str, *args):  # type: ignore[no-untyped-def]
        self.uid_calls.append((command,) + args)
        if command == "MOVE":
            return ("OK", [b""])
        if command == "COPY":
            return ("OK", [b""])
        if command == "STORE":
            return ("OK", [b""])
        if command == "SEARCH":
            return ("OK", [self.search_data])
        if command == "FETCH":
            if args and "(FLAGS)" in args[-1]:
                return ("OK", [(self.fetch_flags_data, b")")])
            return ("OK", [(b"1 (RFC822 {3}", b"hey"), b")"])
        return ("NO", [b"unknown"])

    def append(self, mailbox: str, flags: str, date_time, msg_bytes: bytes):  # type: ignore[no-untyped-def]
        self.append_calls.append((mailbox, flags, date_time, msg_bytes))
        return ("OK", [b"[APPENDUID 1 42]"])

    def expunge(self) -> tuple[str, list[bytes]]:
        return ("OK", [b""])

    def noop(self) -> tuple[str, list[bytes]]:
        return ("OK", [b""])


def test_imap_move_prefers_uid_move(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake = FakeImap(capabilities={b"MOVE"})

    def fake_ctor(host: str, port: int):  # type: ignore[no-untyped-def]
        return fake

    monkeypatch.setattr(imap_client.imaplib, "IMAP4_SSL", fake_ctor)
    c = imap_client.ImapClient(host="h", port=993, username="u", password="p")
    c.connect()
    c.select("INBOX")
    c.move(1, dest_mailbox="ToReply")
    assert ("MOVE", "1", "ToReply") in fake.uid_calls


def test_imap_append_parses_appenduid(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake = FakeImap(capabilities=set())

    def fake_ctor(host: str, port: int):  # type: ignore[no-untyped-def]
        return fake

    monkeypatch.setattr(imap_client.imaplib, "IMAP4_SSL", fake_ctor)
    c = imap_client.ImapClient(host="h", port=993, username="u", password="p")
    c.connect()
    res = c.append("Drafts", b"hi")
    assert res.ok is True
    assert res.appended_uid == 42


def test_imap_ensure_mailbox_uses_inbox_prefix(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake = FakeImap(capabilities=set(), delimiter=".")
    fake._mailboxes.update({"INBOX.Drafts"})

    def fake_ctor(host: str, port: int):  # type: ignore[no-untyped-def]
        return fake

    monkeypatch.setattr(imap_client.imaplib, "IMAP4_SSL", fake_ctor)
    c = imap_client.ImapClient(host="h", port=993, username="u", password="p")
    c.connect()
    c.ensure_mailbox("CalendarCreated")
    assert "INBOX.CalendarCreated" in fake.created


def test_imap_ensure_mailbox_handles_alreadyexists(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Test that ensure_mailbox handles ALREADYEXISTS error gracefully (race condition)."""
    fake = FakeImap(capabilities=set(), delimiter=".")
    fake._mailboxes.update({"INBOX.Drafts"})
    # Simulate race condition: mailbox not in list() but CREATE returns ALREADYEXISTS
    original_create = fake.create

    def create_with_alreadyexists(mailbox: str) -> tuple[str, list[bytes]]:
        if mailbox == "INBOX.Notifications":
            # Simulate ALREADYEXISTS error
            return ("NO", [b"[ALREADYEXISTS] Mailbox already exists (0.001 + 0.000 secs)."])
        return original_create(mailbox)

    fake.create = create_with_alreadyexists

    def fake_ctor(host: str, port: int):  # type: ignore[no-untyped-def]
        return fake

    monkeypatch.setattr(imap_client.imaplib, "IMAP4_SSL", fake_ctor)
    c = imap_client.ImapClient(host="h", port=993, username="u", password="p")
    c.connect()
    # Should not raise an error even though CREATE returns ALREADYEXISTS
    c.ensure_mailbox("Notifications")


def test_imap_uid_search_since_date_builds_query(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake = FakeImap(capabilities=set(), search_data=b"3 4")

    def fake_ctor(host: str, port: int):  # type: ignore[no-untyped-def]
        return fake

    monkeypatch.setattr(imap_client.imaplib, "IMAP4_SSL", fake_ctor)
    c = imap_client.ImapClient(host="h", port=993, username="u", password="p")
    c.connect()
    uids = c.uid_search_since_date(date(2024, 1, 2))
    assert uids == [3, 4]
    assert ("SEARCH", None, "SINCE 02-Jan-2024") in fake.uid_calls


def test_imap_uid_search_header_builds_query(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake = FakeImap(capabilities=set(), search_data=b"10")

    def fake_ctor(host: str, port: int):  # type: ignore[no-untyped-def]
        return fake

    monkeypatch.setattr(imap_client.imaplib, "IMAP4_SSL", fake_ctor)
    c = imap_client.ImapClient(host="h", port=993, username="u", password="p")
    c.connect()
    uids = c.uid_search_header("In-Reply-To", "<msg-1>")
    assert uids == [10]
    assert ('SEARCH', None, 'HEADER In-Reply-To "<msg-1>"') in fake.uid_calls


def test_imap_fetch_flags_parses(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake = FakeImap(
        capabilities=set(),
        fetch_flags_data=b"1 (FLAGS (\\Seen \\Answered))",
    )

    def fake_ctor(host: str, port: int):  # type: ignore[no-untyped-def]
        return fake

    monkeypatch.setattr(imap_client.imaplib, "IMAP4_SSL", fake_ctor)
    c = imap_client.ImapClient(host="h", port=993, username="u", password="p")
    c.connect()
    flags = c.fetch_flags(1)
    assert "\\Seen" in flags
    assert "\\Answered" in flags
