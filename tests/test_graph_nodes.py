from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

from agent.config import Settings
from agent.deps import Deps
from agent.graph import build_email_graph
from agent.llm_openrouter import HeuristicLlm
from agent.models import EmailMeta
from agent.state_store import StateStore


@dataclass
class FakeImap:
    appended: int = 0
    moved: int = 0
    copied: int = 0
    ensured: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.ensured is None:
            self.ensured = []

    def append(self, mailbox: str, msg_bytes: bytes, *, flags=("\\Draft",)):  # type: ignore[no-untyped-def]
        self.appended += 1
        return type("Res", (), {"ok": True, "appended_uid": 999, "raw_response": b""})()

    def ensure_mailbox(self, mailbox: str) -> None:
        self.ensured.append(mailbox)

    def move(self, uid: int, *, dest_mailbox: str) -> None:
        self.moved += 1

    def copy(self, uid: int, *, dest_mailbox: str) -> None:
        self.copied += 1

    def fetch_flags(self, uid: int) -> set[str]:  # noqa: ARG002
        return set()

    def uid_search_header(self, header_name: str, needle: str) -> list[int]:  # noqa: ARG002
        return []

    @contextmanager
    def temporary_select(self, mailbox: str, *, readonly: bool = False):  # noqa: ARG002
        yield None


def test_graph_creates_draft_and_moves(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(
        IMAP_HOST="h",
        IMAP_USERNAME="me@example.com",
        IMAP_PASSWORD="x",
    )
    settings.agent_data_dir = tmp_path
    store = StateStore(tmp_path / "db.sqlite")
    fake_imap = FakeImap()
    deps = Deps(settings=settings, store=store, imap=fake_imap, llm=HeuristicLlm(), calendar=None)  # type: ignore[arg-type]
    graph = build_email_graph(deps)

    meta = EmailMeta(folder="INBOX", uid=1, from_addr="a@example.com", subject="meeting request")
    out = graph.invoke({"meta": meta, "text": "let's schedule a meeting tomorrow"})
    assert out["actions"].create_draft is True
    assert fake_imap.appended == 1
    assert fake_imap.moved == 1
