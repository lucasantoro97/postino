from __future__ import annotations

from agent.config import Settings
from agent.deps import Deps
from agent.imap_client import ImapMessageNotFound
from agent.main import process_one_uid
from agent.state_store import StateStore


class FakeImapMissing:
    def select(self, mailbox: str, *, readonly: bool = False) -> None:  # noqa: ARG002
        return None

    def fetch_flags(self, uid: int) -> set[str]:
        raise ImapMessageNotFound(f"missing uid={uid}")

    def fetch_rfc822(self, uid: int) -> bytes:
        raise ImapMessageNotFound(f"missing uid={uid}")


class GraphShouldNotRun:
    def invoke(self, state):  # type: ignore[no-untyped-def]
        raise AssertionError("graph.invoke should not run when fetch fails")


def test_process_one_uid_skips_missing_message_and_stops_retry_churn(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(IMAP_HOST="h", IMAP_USERNAME="me@example.com", IMAP_PASSWORD="x")
    settings.agent_data_dir = tmp_path
    store = StateStore(tmp_path / "db.sqlite")
    # Seed a record as if a previous run already tracked this UID and it became retryable.
    store.upsert_message_base(
        folder="INBOX",
        uid=1,
        message_id=None,
        subject=None,
        from_addr=None,
        date=None,
        fingerprint="x",
    )

    deps = Deps(
        settings=settings,
        store=store,
        imap=FakeImapMissing(),  # type: ignore[arg-type]
        llm=None,  # type: ignore[arg-type]
        calendar=None,
    )

    process_one_uid(deps=deps, graph=GraphShouldNotRun(), uid=1)
    assert store.seen_message("INBOX", 1) is True
