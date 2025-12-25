from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from .models import ValidatedEvent

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


@dataclass(frozen=True)
class CalendarConfig:
    token_path: Path
    calendar_id: str = "primary"


class GoogleCalendarClient:
    def __init__(self, cfg: CalendarConfig) -> None:
        self._cfg = cfg

    def _load_credentials(self) -> Credentials:
        if not self._cfg.token_path.exists():
            raise RuntimeError(f"Google token not found at {self._cfg.token_path}")
        creds = cast(
            Credentials,
            Credentials.from_authorized_user_file(str(self._cfg.token_path), SCOPES),
        )
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self._cfg.token_path.write_text(creds.to_json())
        return creds

    def create_event(self, event: ValidatedEvent, *, description_extra: str = "") -> str:
        creds = self._load_credentials()
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)

        body: dict[str, Any] = {
            "summary": event.summary,
            "start": {"dateTime": event.start_iso, "timeZone": event.timezone},
            "end": {"dateTime": event.end_iso, "timeZone": event.timezone},
        }
        if event.location:
            body["location"] = event.location
        description = event.description
        if description_extra.strip():
            description = (description + "\n\n" + description_extra).strip()
        if description:
            body["description"] = description

        created = service.events().insert(calendarId=self._cfg.calendar_id, body=body).execute()
        event_id = created.get("id")
        if not event_id:
            raise RuntimeError(
                f"Google Calendar insert returned no id: {json.dumps(created)[:500]}"
            )
        return str(event_id)
