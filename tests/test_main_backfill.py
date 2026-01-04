from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from agent.config import Settings
from agent.deps import Deps
from agent.main import initial_backfill_uids
from agent.state_store import StateStore


@dataclass
class FakeImap:
    since_calls: list[date]
    all_calls: int = 0
    since_uids: list[int] = None  # type: ignore[assignment]
    all_uids: list[int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.since_uids is None:
            self.since_uids = []
        if self.all_uids is None:
            self.all_uids = []

    def uid_search_since_date(self, since_date: date) -> list[int]:
        self.since_calls.append(since_date)
        return list(self.since_uids)

    def uid_search_all(self) -> list[int]:
        self.all_calls += 1
        return list(self.all_uids)


def test_initial_backfill_sets_last_uid(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(IMAP_HOST="h", IMAP_USERNAME="me@example.com", IMAP_PASSWORD="x")
    settings.agent_data_dir = tmp_path
    store = StateStore(tmp_path / "db.sqlite")
    imap = FakeImap(since_calls=[], since_uids=[1, 2], all_uids=[9, 10])
    deps = Deps(settings=settings, store=store, imap=imap, llm=None, calendar=None)  # type: ignore[arg-type]

    uids = initial_backfill_uids(deps=deps, inbox="INBOX", lookback_days=14)
    assert uids == [1, 2]
    assert store.get_last_uid("INBOX") == 10


def test_initial_backfill_zero_days_starts_from_now(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(IMAP_HOST="h", IMAP_USERNAME="me@example.com", IMAP_PASSWORD="x")
    settings.agent_data_dir = tmp_path
    store = StateStore(tmp_path / "db.sqlite")
    imap = FakeImap(since_calls=[], since_uids=[1, 2], all_uids=[9, 10])
    deps = Deps(settings=settings, store=store, imap=imap, llm=None, calendar=None)  # type: ignore[arg-type]

    uids = initial_backfill_uids(deps=deps, inbox="INBOX", lookback_days=0)
    assert uids == []
    # Still records a cursor so subsequent polls only see new mail.
    assert store.get_last_uid("INBOX") == 10
