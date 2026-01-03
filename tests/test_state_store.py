from __future__ import annotations

from agent.models import ClassificationCategory
from agent.state_store import StateStore


def test_state_store_last_uid_roundtrip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = StateStore(tmp_path / "db.sqlite")
    store.set_last_uid("INBOX", 10)
    assert store.get_last_uid("INBOX") == 10


def test_state_store_pending_replies(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = StateStore(tmp_path / "db.sqlite")
    store.upsert_message_base(
        folder="INBOX",
        uid=1,
        message_id="<m1>",
        subject="Subj",
        from_addr="a@example.com",
        date="Mon",
        fingerprint="f",
    )
    store.set_classification(
        folder="INBOX",
        uid=1,
        category=ClassificationCategory.ToReply,
        confidence=0.9,
        rationale="r",
        tags_json="[]",
        reply_needed=True,
        contains_event_request=False,
        priority=10,
    )
    pending = store.pending_reply_messages()
    assert len(pending) == 1
    assert pending[0].uid == 1


def test_state_store_reply_candidates_and_mark_replied(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = StateStore(tmp_path / "db.sqlite")
    store.upsert_message_base(
        folder="INBOX",
        uid=1,
        message_id="<m1>",
        subject="Subj",
        from_addr="a@example.com",
        date="Mon",
        fingerprint="f",
    )
    store.set_classification(
        folder="INBOX",
        uid=1,
        category=ClassificationCategory.ToReply,
        confidence=0.9,
        rationale="r",
        tags_json="[]",
        reply_needed=True,
        contains_event_request=False,
        priority=10,
    )
    store.set_filing_result(folder="INBOX", uid=1, filing_folder="ToReply", status="moved")
    candidates = store.reply_candidates(filing_folder="ToReply")
    assert len(candidates) == 1
    store.mark_replied("INBOX", 1, replied_folder="Replied")
    candidates = store.reply_candidates(filing_folder="ToReply")
    assert len(candidates) == 0


def test_state_store_replied_moves(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = StateStore(tmp_path / "db.sqlite")
    store.record_replied_move(
        local_date="2025-01-01",
        message_id="<m1>",
        subject="Subj",
        from_addr="a@example.com",
    )
    moves = store.replied_moves_for_date(local_date="2025-01-01")
    assert len(moves) == 1
    assert moves[0].message_id == "<m1>"


def test_state_store_replied_moves_since_and_digest_run_tracking(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = StateStore(tmp_path / "db.sqlite")
    assert store.replied_digest_last_created_at() is None
    store.record_replied_digest_run(draft_uid=123)
    assert store.replied_digest_last_created_at() is not None

    # moved_at is stored as UTC ISO; use a low since_utc_iso so the row is included.
    store.record_replied_move(
        local_date="2025-01-01",
        message_id="<m2>",
        subject="Subj2",
        from_addr="b@example.com",
    )
    moves = store.replied_moves_since(since_utc_iso="1970-01-01T00:00:00+00:00")
    assert len(moves) >= 1
