from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .google_calendar import GoogleCalendarClient
from .imap_client import ImapClient
from .llm_openrouter import LlmClient
from .state_store import StateStore


@dataclass(frozen=True)
class Deps:
    settings: Settings
    store: StateStore
    imap: ImapClient
    llm: LlmClient
    calendar: GoogleCalendarClient | None
