from __future__ import annotations

import imaplib
import re
import socket
from contextlib import contextmanager
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, cast
from datetime import date

_APPENDUID_RE = re.compile(rb"APPENDUID \d+ (\d+)")
_LIST_QUOTED_RE = re.compile(rb'"([^"]*)"')
_FLAGS_RE = re.compile(rb"FLAGS \(([^)]*)\)")


@dataclass(frozen=True)
class ImapAppendResult:
    ok: bool
    appended_uid: int | None = None
    raw_response: bytes | None = None


class ImapClient:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        timeout: float = 30.0,
        mailbox_prefix: str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._timeout = timeout
        self._imap: imaplib.IMAP4_SSL | None = None
        self._mailbox_prefix = mailbox_prefix
        self._delimiter: str | None = None
        self._selected_mailbox: str | None = None
        self._selected_readonly: bool = False

    def __enter__(self) -> ImapClient:
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.logout()

    def connect(self) -> None:
        socket.setdefaulttimeout(self._timeout)
        self._imap = imaplib.IMAP4_SSL(self._host, self._port)
        self._imap.login(self._username, self._password)
        self._discover_namespace()

    def logout(self) -> None:
        if self._imap is None:
            return
        try:
            self._imap.logout()
        finally:
            self._imap = None

    @property
    def capabilities(self) -> set[str]:
        if self._imap is None:
            return set()
        caps = getattr(self._imap, "capabilities", None)
        if caps is None:
            typ, data = self._imap.capability()
            if typ != "OK":
                return set()
            caps = set(b" ".join(data).split())
        out: set[str] = set()
        for c in caps:
            if isinstance(c, (bytes, bytearray)):
                out.add(c.decode(errors="replace"))
            elif isinstance(c, str):
                out.add(c)
        return out

    def _discover_namespace(self) -> None:
        if self._imap is None:
            return
        if self._mailbox_prefix is not None:
            return
        typ, data = cast(tuple[str, list[bytes]], self._imap.list())
        if typ != "OK":
            return

        delims: list[str] = []
        names: list[str] = []
        for line in data:
            if not line:
                continue
            parts = _LIST_QUOTED_RE.findall(line)
            if len(parts) >= 2:
                delims.append(parts[-2].decode(errors="replace"))
                names.append(parts[-1].decode(errors="replace"))
            elif len(parts) == 1:
                names.append(parts[-1].decode(errors="replace"))

        if delims:
            self._delimiter = max(set(delims), key=delims.count)

        if self._delimiter and any(
            name.startswith(f"INBOX{self._delimiter}") and name != "INBOX" for name in names
        ):
            self._mailbox_prefix = f"INBOX{self._delimiter}"
            return
        if any(name.startswith("INBOX.") and name != "INBOX" for name in names):
            self._mailbox_prefix = "INBOX."
            return
        if any(name.startswith("INBOX/") and name != "INBOX" for name in names):
            self._mailbox_prefix = "INBOX/"

    def _resolve_mailbox(self, mailbox: str) -> str:
        if not mailbox:
            return mailbox
        if mailbox.upper().startswith("INBOX"):
            return mailbox
        if self._mailbox_prefix:
            return f"{self._mailbox_prefix}{mailbox}"
        return mailbox

    def list_mailboxes(self) -> list[str]:
        assert self._imap is not None
        typ, data = cast(tuple[str, list[bytes]], self._imap.list())
        if typ != "OK":
            raise RuntimeError(f"IMAP LIST failed: {typ} {data}")
        names: list[str] = []
        for line in data:
            if not line:
                continue
            parts = _LIST_QUOTED_RE.findall(line)
            if parts:
                names.append(parts[-1].decode(errors="replace"))
            else:
                decoded = line.decode(errors="replace")
                if " " in decoded:
                    name = decoded.split(" ", maxsplit=2)[-1].strip().strip('"')
                    names.append(name)
        return names

    def ensure_mailbox(self, mailbox: str) -> None:
        assert self._imap is not None
        existing = set(self.list_mailboxes())
        resolved = self._resolve_mailbox(mailbox)
        if resolved in existing:
            return
        typ, data = cast(tuple[str, list[bytes]], self._imap.create(resolved))
        if typ != "OK":
            msg = b" ".join(data or [])
            # If mailbox already exists (race condition), treat as success
            if b"ALREADYEXISTS" in msg:
                return
            if self._mailbox_prefix is None and b"prefixed with: INBOX" in msg:
                # Common server hint (e.g. Dovecot): create mailboxes under INBOX namespace.
                self._mailbox_prefix = f"INBOX{self._delimiter or '.'}"
                resolved_retry = self._resolve_mailbox(mailbox)
                typ, data = cast(tuple[str, list[bytes]], self._imap.create(resolved_retry))
                if typ != "OK":
                    msg_retry = b" ".join(data or [])
                    # Check for ALREADYEXISTS on retry as well
                    if b"ALREADYEXISTS" in msg_retry:
                        return
        if typ != "OK":
            raise RuntimeError(f"IMAP CREATE {mailbox} failed: {typ} {data}")

    def select(self, mailbox: str, *, readonly: bool = False) -> None:
        assert self._imap is not None
        typ, data = cast(
            tuple[str, list[bytes]],
            self._imap.select(self._resolve_mailbox(mailbox), readonly=readonly),
        )
        if typ != "OK":
            raise RuntimeError(f"IMAP SELECT {mailbox} failed: {typ} {data}")
        self._selected_mailbox = mailbox
        self._selected_readonly = readonly

    @contextmanager
    def temporary_select(self, mailbox: str, *, readonly: bool = False) -> Iterable[None]:
        previous = self._selected_mailbox
        previous_readonly = self._selected_readonly
        self.select(mailbox, readonly=readonly)
        try:
            yield None
        finally:
            if previous:
                self.select(previous, readonly=previous_readonly)

    def uid_search_since(self, last_uid: int) -> list[int]:
        assert self._imap is not None
        query = f"UID {last_uid + 1}:*"
        typ, data = cast(
            tuple[str, list[bytes]],
            self._imap.uid("SEARCH", None, query),  # type: ignore[arg-type]
        )
        if typ != "OK":
            raise RuntimeError(f"IMAP UID SEARCH failed: {typ} {data}")
        if not data or not data[0]:
            return []
        return [int(x) for x in data[0].split()]

    def uid_search_since_date(self, since_date: date) -> list[int]:
        assert self._imap is not None
        query = f"SINCE {self._format_imap_date(since_date)}"
        typ, data = cast(
            tuple[str, list[bytes]],
            self._imap.uid("SEARCH", None, query),  # type: ignore[arg-type]
        )
        if typ != "OK":
            raise RuntimeError(f"IMAP UID SEARCH failed: {typ} {data}")
        if not data or not data[0]:
            return []
        return [int(x) for x in data[0].split()]

    def uid_search_all(self) -> list[int]:
        assert self._imap is not None
        typ, data = cast(
            tuple[str, list[bytes]],
            self._imap.uid("SEARCH", None, "ALL"),  # type: ignore[arg-type]
        )
        if typ != "OK":
            raise RuntimeError(f"IMAP UID SEARCH failed: {typ} {data}")
        if not data or not data[0]:
            return []
        return [int(x) for x in data[0].split()]

    def uid_search_header(self, header_name: str, needle: str) -> list[int]:
        assert self._imap is not None
        escaped = needle.replace('"', '\\"')
        query = f'HEADER {header_name} "{escaped}"'
        typ, data = cast(
            tuple[str, list[bytes]],
            self._imap.uid("SEARCH", None, query),  # type: ignore[arg-type]
        )
        if typ != "OK":
            raise RuntimeError(f"IMAP UID SEARCH failed: {typ} {data}")
        if not data or not data[0]:
            return []
        return [int(x) for x in data[0].split()]

    def fetch_rfc822(self, uid: int) -> bytes:
        assert self._imap is not None
        typ, data = cast(tuple[str, list[Any]], self._imap.uid("FETCH", str(uid), "(RFC822)"))
        if typ != "OK" or not data or not data[0]:
            raise RuntimeError(f"IMAP UID FETCH failed: {typ} {data}")
        # data can be [(b'UID ...', b'raw...'), b')']
        for item in data:
            if (
                isinstance(item, tuple)
                and len(item) == 2
                and isinstance(item[1], (bytes, bytearray))
            ):
                return bytes(item[1])
        raise RuntimeError(f"IMAP UID FETCH: unexpected response: {data}")

    def fetch_flags(self, uid: int) -> set[str]:
        assert self._imap is not None
        typ, data = cast(tuple[str, list[Any]], self._imap.uid("FETCH", str(uid), "(FLAGS)"))
        if typ != "OK" or not data:
            raise RuntimeError(f"IMAP UID FETCH failed: {typ} {data}")
        for item in data:
            if isinstance(item, tuple) and item and isinstance(item[0], (bytes, bytearray)):
                m = _FLAGS_RE.search(item[0])
                if not m:
                    continue
                raw_flags = m.group(1).decode(errors="replace").strip()
                if not raw_flags:
                    return set()
                return set(raw_flags.split())
        return set()

    def append(
        self,
        mailbox: str,
        msg_bytes: bytes,
        *,
        flags: Iterable[str] = ("\\Draft",),
    ) -> ImapAppendResult:
        assert self._imap is not None
        resolved = self._resolve_mailbox(mailbox)
        flag_str = f"({' '.join(flags)})"
        typ, data = cast(
            tuple[str, list[bytes]],
            self._imap.append(resolved, flag_str, None, msg_bytes),  # type: ignore[arg-type]
        )
        if typ != "OK":
            return ImapAppendResult(ok=False, raw_response=data[0] if data else None)
        appended_uid: int | None = None
        if data and data[0]:
            m = _APPENDUID_RE.search(data[0])
            if m:
                appended_uid = int(m.group(1))
        raw = data[0] if data else None
        return ImapAppendResult(ok=True, appended_uid=appended_uid, raw_response=raw)

    def move(self, uid: int, *, dest_mailbox: str) -> None:
        assert self._imap is not None
        resolved = self._resolve_mailbox(dest_mailbox)
        if "MOVE" in self.capabilities:
            typ, data = self._imap.uid("MOVE", str(uid), resolved)
            if typ == "OK":
                return
        # Fallback: COPY + delete + expunge
        typ, data = self._imap.uid("COPY", str(uid), resolved)
        if typ != "OK":
            raise RuntimeError(f"IMAP UID COPY failed: {typ} {data}")
        typ, data = self._imap.uid("STORE", str(uid), "+FLAGS.SILENT", "(\\Deleted)")
        if typ != "OK":
            raise RuntimeError(f"IMAP UID STORE +Deleted failed: {typ} {data}")
        typ, data = self._imap.expunge()
        if typ != "OK":
            raise RuntimeError(f"IMAP EXPUNGE failed: {typ} {data}")

    def copy(self, uid: int, *, dest_mailbox: str) -> None:
        assert self._imap is not None
        typ, data = self._imap.uid("COPY", str(uid), self._resolve_mailbox(dest_mailbox))
        if typ != "OK":
            raise RuntimeError(f"IMAP UID COPY failed: {typ} {data}")

    def noop(self) -> None:
        assert self._imap is not None
        self._imap.noop()

    @staticmethod
    def _format_imap_date(value: date) -> str:
        return value.strftime("%d-%b-%Y")
