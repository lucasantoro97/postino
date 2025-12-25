from __future__ import annotations

from dataclasses import dataclass

from agent.config import Settings
from agent.deps import Deps
from agent.models import ActionPlan, EmailMeta, ValidatedEvent
from agent.nodes.create_calendar_event import create_calendar_event_node
from agent.state_store import StateStore


@dataclass
class FakeCalendar:
    created: list[str]

    def create_event(self, event: ValidatedEvent, description_extra: str) -> str:  # noqa: ARG002
        self.created.append(event.summary)
        return "evt-123"


def test_calendar_creation_persists_event(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(IMAP_HOST="h", IMAP_USERNAME="me@example.com", IMAP_PASSWORD="x")
    settings.agent_data_dir = tmp_path
    store = StateStore(tmp_path / "db.sqlite")
    calendar = FakeCalendar(created=[])
    deps = Deps(settings=settings, store=store, imap=None, llm=None, calendar=calendar)  # type: ignore[arg-type]

    meta = EmailMeta(folder="INBOX", uid=1)
    store.upsert_message_base(
        folder="INBOX",
        uid=1,
        message_id=None,
        subject=None,
        from_addr=None,
        date=None,
        fingerprint="x",
    )
    event = ValidatedEvent(
        summary="Sync",
        start_iso="2024-01-01T10:00:00Z",
        end_iso="2024-01-01T10:30:00Z",
        timezone="UTC",
        description="Meet",
    )
    state = {"actions": ActionPlan(create_calendar_event=True), "meta": meta, "validated_event": event}
    out = create_calendar_event_node(state, deps)
    assert out["calendar_event_id"] == "evt-123"
    assert store.get_message_calendar_event_id("INBOX", 1) == "evt-123"
    assert calendar.created == ["Sync"]


def test_calendar_missing_does_not_raise(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(IMAP_HOST="h", IMAP_USERNAME="me@example.com", IMAP_PASSWORD="x")
    settings.agent_data_dir = tmp_path
    store = StateStore(tmp_path / "db.sqlite")
    deps = Deps(settings=settings, store=store, imap=None, llm=None, calendar=None)  # type: ignore[arg-type]

    meta = EmailMeta(folder="INBOX", uid=1)
    store.upsert_message_base(
        folder="INBOX",
        uid=1,
        message_id=None,
        subject=None,
        from_addr=None,
        date=None,
        fingerprint="x",
    )
    event = ValidatedEvent(
        summary="Sync",
        start_iso="2024-01-01T10:00:00Z",
        end_iso="2024-01-01T10:30:00Z",
        timezone="UTC",
        description="Meet",
    )
    state = {"actions": ActionPlan(create_calendar_event=True), "meta": meta, "validated_event": event}
    out = create_calendar_event_node(state, deps)
    assert out.get("calendar_event_id") is None
