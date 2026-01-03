from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import ClassificationCategory


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class RecentMessage:
    folder: str
    uid: int
    subject: str | None
    from_addr: str | None
    date: str | None
    category: str | None
    confidence: float | None
    priority: int | None
    filing_folder: str | None
    draft_uid: int | None
    calendar_event_id: str | None


@dataclass(frozen=True)
class ReplyCandidate:
    folder: str
    uid: int
    message_id: str | None
    subject: str | None
    from_addr: str | None
    date: str | None
    filing_folder: str | None


@dataclass(frozen=True)
class RepliedMove:
    message_id: str | None
    subject: str | None
    from_addr: str | None


class StateStore:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    def close(self) -> None:
        self._conn.close()

    def _migrate(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS folder_state (
              folder TEXT PRIMARY KEY,
              last_uid INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
              folder TEXT NOT NULL,
              uid INTEGER NOT NULL,
              message_id TEXT,
              subject TEXT,
              from_addr TEXT,
              date TEXT,
              fingerprint TEXT,
              priority INTEGER,
              category TEXT,
              confidence REAL,
              rationale TEXT,
              tags_json TEXT,
              reply_needed INTEGER,
              contains_event_request INTEGER,
              filing_folder TEXT,
              filing_status TEXT,
              draft_uid INTEGER,
              calendar_event_id TEXT,
              last_error TEXT,
              attempts INTEGER NOT NULL DEFAULT 0,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(folder, uid)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS executive_briefs (
              local_date TEXT PRIMARY KEY,
              draft_uid INTEGER,
              created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_recaps (
              local_date TEXT PRIMARY KEY,
              draft_uid INTEGER,
              created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS weekly_recaps (
              week_key TEXT PRIMARY KEY,
              draft_uid INTEGER,
              created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS replied_digests (
              local_date TEXT PRIMARY KEY,
              draft_uid INTEGER,
              created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS replied_moves (
              local_date TEXT NOT NULL,
              message_id TEXT,
              subject TEXT,
              from_addr TEXT,
              moved_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def get_last_uid(self, folder: str) -> int:
        row = self._conn.execute(
            "SELECT last_uid FROM folder_state WHERE folder=?",
            (folder,),
        ).fetchone()
        return int(row["last_uid"]) if row else 0

    def set_last_uid(self, folder: str, last_uid: int) -> None:
        self._conn.execute(
            "INSERT INTO folder_state(folder,last_uid) VALUES(?,?) "
            "ON CONFLICT(folder) DO UPDATE SET last_uid=excluded.last_uid",
            (folder, int(last_uid)),
        )
        self._conn.commit()

    def seen_message(self, folder: str, uid: int) -> bool:
        row = self._conn.execute(
            """
            SELECT 1
            FROM messages
            WHERE folder=? AND uid=? AND filing_status IN ('moved', 'skipped', 'replied')
            """,
            (folder, uid),
        ).fetchone()
        return row is not None

    def upsert_message_base(
        self,
        *,
        folder: str,
        uid: int,
        message_id: str | None,
        subject: str | None,
        from_addr: str | None,
        date: str | None,
        fingerprint: str,
    ) -> None:
        now = _utc_now().isoformat()
        self._conn.execute(
            """
            INSERT INTO messages(
              folder,uid,message_id,subject,from_addr,date,fingerprint,updated_at
            )
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(folder,uid) DO UPDATE SET
              message_id=COALESCE(excluded.message_id, message_id),
              subject=COALESCE(excluded.subject, subject),
              from_addr=COALESCE(excluded.from_addr, from_addr),
              date=COALESCE(excluded.date, date),
              fingerprint=excluded.fingerprint,
              updated_at=excluded.updated_at
            """,
            (folder, uid, message_id, subject, from_addr, date, fingerprint, now),
        )
        self._conn.commit()

    def record_attempt(self, folder: str, uid: int, *, error: str | None = None) -> None:
        now = _utc_now().isoformat()
        self._conn.execute(
            """
            UPDATE messages
            SET attempts=attempts+1, last_error=?, updated_at=?
            WHERE folder=? AND uid=?
            """,
            (error, now, folder, uid),
        )
        self._conn.commit()

    def set_classification(
        self,
        *,
        folder: str,
        uid: int,
        category: ClassificationCategory,
        confidence: float,
        rationale: str,
        tags_json: str,
        reply_needed: bool,
        contains_event_request: bool,
        priority: int,
    ) -> None:
        now = _utc_now().isoformat()
        self._conn.execute(
            """
            UPDATE messages
            SET category=?, confidence=?, rationale=?, tags_json=?, reply_needed=?,
                contains_event_request=?,
                priority=?, updated_at=?
            WHERE folder=? AND uid=?
            """,
            (
                category.value,
                float(confidence),
                rationale,
                tags_json,
                1 if reply_needed else 0,
                1 if contains_event_request else 0,
                int(priority),
                now,
                folder,
                uid,
            ),
        )
        self._conn.commit()

    def set_draft_uid(self, folder: str, uid: int, draft_uid: int | None) -> None:
        now = _utc_now().isoformat()
        self._conn.execute(
            "UPDATE messages SET draft_uid=?, updated_at=? WHERE folder=? AND uid=?",
            (draft_uid, now, folder, uid),
        )
        self._conn.commit()

    def set_calendar_event_id(self, folder: str, uid: int, event_id: str | None) -> None:
        now = _utc_now().isoformat()
        self._conn.execute(
            "UPDATE messages SET calendar_event_id=?, updated_at=? WHERE folder=? AND uid=?",
            (event_id, now, folder, uid),
        )
        self._conn.commit()

    def set_filing_result(self, folder: str, uid: int, *, filing_folder: str, status: str) -> None:
        now = _utc_now().isoformat()
        self._conn.execute(
            "UPDATE messages SET filing_folder=?, filing_status=?, updated_at=? "
            "WHERE folder=? AND uid=?",
            (filing_folder, status, now, folder, uid),
        )
        self._conn.commit()

    def get_message_draft_uid(self, folder: str, uid: int) -> int | None:
        row = self._conn.execute(
            "SELECT draft_uid FROM messages WHERE folder=? AND uid=?",
            (folder, uid),
        ).fetchone()
        return int(row["draft_uid"]) if row and row["draft_uid"] is not None else None

    def get_message_calendar_event_id(self, folder: str, uid: int) -> str | None:
        row = self._conn.execute(
            "SELECT calendar_event_id FROM messages WHERE folder=? AND uid=?", (folder, uid)
        ).fetchone()
        return (
            str(row["calendar_event_id"]) if row and row["calendar_event_id"] is not None else None
        )

    def recent_messages(self, *, lookback_hours: int) -> list[RecentMessage]:
        since = (_utc_now() - timedelta(hours=lookback_hours)).isoformat()
        rows = self._conn.execute(
            """
            SELECT folder, uid, subject, from_addr, date, category, confidence, priority,
                   filing_folder, draft_uid, calendar_event_id
            FROM messages
            WHERE updated_at >= ?
            ORDER BY COALESCE(priority, 0) DESC, updated_at DESC
            """,
            (since,),
        ).fetchall()
        return [RecentMessage(**dict(r)) for r in rows]

    def recent_category_counts(self, *, lookback_hours: int) -> list[tuple[str, int]]:
        since = (_utc_now() - timedelta(hours=lookback_hours)).isoformat()
        rows = self._conn.execute(
            """
            SELECT COALESCE(category, 'Unknown') AS category, COUNT(*) AS cnt
            FROM messages
            WHERE updated_at >= ?
            GROUP BY category
            ORDER BY cnt DESC, category ASC
            """,
            (since,),
        ).fetchall()
        return [(str(r["category"]), int(r["cnt"])) for r in rows]

    def recent_calendar_messages(self, *, lookback_hours: int) -> list[RecentMessage]:
        since = (_utc_now() - timedelta(hours=lookback_hours)).isoformat()
        rows = self._conn.execute(
            """
            SELECT folder, uid, subject, from_addr, date, category, confidence, priority,
                   filing_folder, draft_uid, calendar_event_id
            FROM messages
            WHERE updated_at >= ? AND calendar_event_id IS NOT NULL
            ORDER BY updated_at DESC
            """,
            (since,),
        ).fetchall()
        return [RecentMessage(**dict(r)) for r in rows]

    def recent_draft_messages(self, *, lookback_hours: int) -> list[RecentMessage]:
        since = (_utc_now() - timedelta(hours=lookback_hours)).isoformat()
        rows = self._conn.execute(
            """
            SELECT folder, uid, subject, from_addr, date, category, confidence, priority,
                   filing_folder, draft_uid, calendar_event_id
            FROM messages
            WHERE updated_at >= ? AND draft_uid IS NOT NULL AND draft_uid != 0
            ORDER BY updated_at DESC
            """,
            (since,),
        ).fetchall()
        return [RecentMessage(**dict(r)) for r in rows]

    def retryable_uids(
        self,
        folder: str,
        *,
        min_age_seconds: int = 60,
        limit: int = 50,
    ) -> list[int]:
        cutoff = (_utc_now() - timedelta(seconds=min_age_seconds)).isoformat()
        rows = self._conn.execute(
            """
            SELECT uid
            FROM messages
            WHERE folder=?
              AND attempts>0
              AND (filing_status IS NULL OR filing_status NOT IN ('moved', 'skipped', 'replied'))
              AND updated_at <= ?
            ORDER BY updated_at ASC
            LIMIT ?
            """,
            (folder, cutoff, int(limit)),
        ).fetchall()
        return [int(r["uid"]) for r in rows]

    def pending_reply_messages(self) -> list[RecentMessage]:
        rows = self._conn.execute(
            """
            SELECT folder, uid, subject, from_addr, date, category, confidence, priority,
                   filing_folder, draft_uid, calendar_event_id
            FROM messages
            WHERE reply_needed=1 AND (draft_uid IS NULL OR draft_uid=0)
            ORDER BY COALESCE(priority, 0) DESC, updated_at DESC
            """
        ).fetchall()
        return [RecentMessage(**dict(r)) for r in rows]

    def reply_candidates(self, *, filing_folder: str) -> list[ReplyCandidate]:
        rows = self._conn.execute(
            """
            SELECT folder, uid, message_id, subject, from_addr, date, filing_folder
            FROM messages
            WHERE reply_needed=1 AND message_id IS NOT NULL AND filing_folder=?
            ORDER BY updated_at DESC
            """,
            (filing_folder,),
        ).fetchall()
        return [ReplyCandidate(**dict(r)) for r in rows]

    def mark_replied(self, folder: str, uid: int, *, replied_folder: str) -> None:
        now = _utc_now().isoformat()
        self._conn.execute(
            """
            UPDATE messages
            SET reply_needed=0, filing_folder=?, filing_status='replied', updated_at=?
            WHERE folder=? AND uid=?
            """,
            (replied_folder, now, folder, uid),
        )
        self._conn.commit()

    def executive_brief_exists(self, *, local_date: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM executive_briefs WHERE local_date=?",
            (local_date,),
        ).fetchone()
        return row is not None

    def record_executive_brief(self, *, local_date: str, draft_uid: int | None) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO executive_briefs(local_date, draft_uid, created_at) "
            "VALUES(?,?,?)",
            (local_date, draft_uid, _utc_now().isoformat()),
        )
        self._conn.commit()

    def daily_recap_exists(self, *, local_date: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM daily_recaps WHERE local_date=?",
            (local_date,),
        ).fetchone()
        return row is not None

    def record_daily_recap(self, *, local_date: str, draft_uid: int | None) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO daily_recaps(local_date, draft_uid, created_at) VALUES(?,?,?)",
            (local_date, draft_uid, _utc_now().isoformat()),
        )
        self._conn.commit()

    def weekly_recap_exists(self, *, week_key: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM weekly_recaps WHERE week_key=?",
            (week_key,),
        ).fetchone()
        return row is not None

    def record_weekly_recap(self, *, week_key: str, draft_uid: int | None) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO weekly_recaps(week_key, draft_uid, created_at) VALUES(?,?,?)",
            (week_key, draft_uid, _utc_now().isoformat()),
        )
        self._conn.commit()

    def replied_digest_exists(self, *, local_date: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM replied_digests WHERE local_date=?",
            (local_date,),
        ).fetchone()
        return row is not None

    def record_replied_digest(self, *, local_date: str, draft_uid: int | None) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO replied_digests(local_date, draft_uid, created_at) "
            "VALUES(?,?,?)",
            (local_date, draft_uid, _utc_now().isoformat()),
        )
        self._conn.commit()

    def record_replied_move(
        self,
        *,
        local_date: str,
        message_id: str | None,
        subject: str | None,
        from_addr: str | None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO replied_moves(local_date, message_id, subject, from_addr, moved_at) "
            "VALUES(?,?,?,?,?)",
            (local_date, message_id, subject, from_addr, _utc_now().isoformat()),
        )
        self._conn.commit()

    def replied_moves_for_date(self, *, local_date: str) -> list[RepliedMove]:
        rows = self._conn.execute(
            """
            SELECT message_id, subject, from_addr
            FROM replied_moves
            WHERE local_date=?
            ORDER BY moved_at DESC
            """,
            (local_date,),
        ).fetchall()
        return [RepliedMove(**dict(r)) for r in rows]
