from __future__ import annotations

from contextlib import contextmanager
from email import policy
from email.parser import BytesParser

from agent.config import Settings
from agent.deps import Deps
from agent.llm_openrouter import HeuristicLlm
from agent.models import ActionPlan, EmailMeta, ReplyDraft
from agent.nodes.draft_reply import draft_reply_node
from agent.state_store import StateStore


class FakeImap:
    def __init__(self, *, flags: set[str] | None = None, sent_hits: list[int] | None = None):
        self.flags = flags or set()
        self.sent_hits = sent_hits or []
        self.appended: list[bytes] = []

    def fetch_flags(self, uid: int) -> set[str]:  # noqa: ARG002
        return set(self.flags)

    def uid_search_header(self, header_name: str, needle: str) -> list[int]:  # noqa: ARG002
        return list(self.sent_hits)

    @contextmanager
    def temporary_select(self, mailbox: str, *, readonly: bool = False):  # noqa: ARG002
        yield None

    def append(self, mailbox: str, msg_bytes: bytes, *, flags=("\\Draft",)):  # type: ignore[no-untyped-def] # noqa: ARG002
        self.appended.append(msg_bytes)
        return type("Res", (), {"ok": True, "appended_uid": 555, "raw_response": b""})()


class QuoteOnlyLlm:
    def classify(self, *, meta, text):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def draft_reply(self, *, meta, text):  # type: ignore[no-untyped-def]
        return ReplyDraft(
            to_addr=meta.from_addr or "",
            subject="Re: test",
            body="On Fri, X wrote:\n> quoted",
            in_reply_to=meta.message_id,
            references=None,
        )

    def extract_events(self, *, meta, text):  # type: ignore[no-untyped-def]
        return []


def _build_state(meta: EmailMeta, text: str) -> dict[str, object]:
    return {"actions": ActionPlan(create_draft=True), "meta": meta, "text": text}


def test_draft_includes_original_and_thread_headers(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(IMAP_HOST="h", IMAP_USERNAME="me@example.com", IMAP_PASSWORD="x")
    settings.agent_data_dir = tmp_path
    store = StateStore(tmp_path / "db.sqlite")
    imap = FakeImap()
    deps = Deps(settings=settings, store=store, imap=imap, llm=HeuristicLlm(), calendar=None)  # type: ignore[arg-type]

    meta = EmailMeta(
        folder="INBOX",
        uid=1,
        from_addr="a@example.com",
        to_addr="me@example.com, team@example.com",
        to_addrs=["me@example.com", "team@example.com"],
        subject="Meeting",
        message_id="<msg-1>",
        references=["<ref-0>"],
        date="Mon, 1 Jan 2024 10:00:00 +0000",
    )
    state = _build_state(meta, "Hello\nWorld")
    draft_reply_node(state, deps)
    assert len(imap.appended) == 1
    msg = BytesParser(policy=policy.default).parsebytes(imap.appended[0])
    assert msg["In-Reply-To"] == "<msg-1>"
    assert msg["References"] == "<ref-0> <msg-1>"
    assert msg["Cc"] == "team@example.com"
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert "On Mon, 1 Jan 2024 10:00:00 +0000, a@example.com wrote:" in body
    assert "From: a@example.com" in body
    assert "To: me@example.com, team@example.com" in body
    assert "Date: Mon, 1 Jan 2024 10:00:00 +0000" in body
    assert "> Hello" in body
    assert "> World" in body


def test_draft_skipped_when_answered(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(IMAP_HOST="h", IMAP_USERNAME="me@example.com", IMAP_PASSWORD="x")
    settings.agent_data_dir = tmp_path
    store = StateStore(tmp_path / "db.sqlite")
    imap = FakeImap(flags={"\\Answered"})
    deps = Deps(settings=settings, store=store, imap=imap, llm=HeuristicLlm(), calendar=None)  # type: ignore[arg-type]

    meta = EmailMeta(folder="INBOX", uid=2, from_addr="a@example.com", subject="Hi")
    state = _build_state(meta, "Thanks")
    draft_reply_node(state, deps)
    assert len(imap.appended) == 0


def test_draft_skipped_when_sent_match(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(
        IMAP_HOST="h",
        IMAP_USERNAME="me@example.com",
        IMAP_PASSWORD="x",
        IMAP_SENT_FOLDER="Sent",
    )
    settings.agent_data_dir = tmp_path
    store = StateStore(tmp_path / "db.sqlite")
    imap = FakeImap(sent_hits=[10])
    deps = Deps(settings=settings, store=store, imap=imap, llm=HeuristicLlm(), calendar=None)  # type: ignore[arg-type]

    meta = EmailMeta(
        folder="INBOX",
        uid=3,
        from_addr="a@example.com",
        subject="Hi",
        message_id="<msg-1>",
    )
    state = _build_state(meta, "Thanks")
    draft_reply_node(state, deps)
    assert len(imap.appended) == 0


def test_draft_skipped_when_not_addressed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(IMAP_HOST="h", IMAP_USERNAME="me@example.com", IMAP_PASSWORD="x")
    settings.agent_data_dir = tmp_path
    store = StateStore(tmp_path / "db.sqlite")
    imap = FakeImap()
    deps = Deps(settings=settings, store=store, imap=imap, llm=HeuristicLlm(), calendar=None)  # type: ignore[arg-type]

    meta = EmailMeta(
        folder="INBOX",
        uid=4,
        from_addr="a@example.com",
        to_addr="other@example.com",
        to_addrs=["other@example.com"],
        subject="Hi",
    )
    state = _build_state(meta, "Thanks")
    draft_reply_node(state, deps)
    assert len(imap.appended) == 0


def test_draft_fallback_when_no_meaningful_reply(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(IMAP_HOST="h", IMAP_USERNAME="me@example.com", IMAP_PASSWORD="x")
    settings.agent_data_dir = tmp_path
    store = StateStore(tmp_path / "db.sqlite")
    imap = FakeImap()
    deps = Deps(settings=settings, store=store, imap=imap, llm=QuoteOnlyLlm(), calendar=None)  # type: ignore[arg-type]

    meta = EmailMeta(
        folder="INBOX",
        uid=5,
        from_addr="a@example.com",
        to_addr="me@example.com",
        to_addrs=["me@example.com"],
        subject="Hello",
    )
    state = _build_state(meta, "Hi")
    draft_reply_node(state, deps)
    msg = BytesParser(policy=policy.default).parsebytes(imap.appended[0])
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert "Grazie per la tua email." in body or "Thanks for your email." in body
