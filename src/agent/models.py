from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ClassificationCategory(str, Enum):
    ToReply = "ToReply"
    Receipts = "Receipts"
    Newsletters = "Newsletters"
    Notifications = "Notifications"
    CalendarCreated = "CalendarCreated"
    NoAction = "NoAction"
    NeedsReview = "NeedsReview"


class EmailMeta(BaseModel):
    folder: str
    uid: int
    message_id: str | None = None
    in_reply_to: str | None = None
    references: list[str] = Field(default_factory=list)
    from_addr: str | None = None
    to_addr: str | None = None
    cc_addr: str | None = None
    to_addrs: list[str] = Field(default_factory=list)
    cc_addrs: list[str] = Field(default_factory=list)
    subject: str | None = None
    date: str | None = None
    reply_to: str | None = None


class ClassificationResult(BaseModel):
    category: ClassificationCategory
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    tags: list[str] = Field(default_factory=list)
    reply_needed: bool = False
    contains_event_request: bool = False


class ActionPlan(BaseModel):
    create_draft: bool = False
    extract_event: bool = False
    create_calendar_event: bool = False
    file_email: bool = True


class ReplyDraft(BaseModel):
    to_addr: str
    cc_addrs: list[str] = Field(default_factory=list)
    subject: str
    body: str
    in_reply_to: str | None = None
    references: str | None = None


class EventCandidate(BaseModel):
    summary: str
    start: str
    end: str | None = None
    duration_minutes: int | None = None
    timezone: str | None = None
    location: str | None = None
    evidence: list[str] = Field(default_factory=list)


class ValidatedEvent(BaseModel):
    summary: str
    start_iso: str
    end_iso: str
    timezone: str
    location: str | None = None
    description: str


FilingMode = Literal["move", "copy"]
