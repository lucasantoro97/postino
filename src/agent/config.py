from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _loads_json(value: str | None, *, default: Any) -> Any:
    if value is None or value.strip() == "":
        return default
    return json.loads(value)


DEFAULT_CLASSIFICATION_FOLDERS: dict[str, str] = {
    "ToReply": "ToReply",
    "Receipts": "Receipts",
    "Newsletters": "Newsletters",
    "Notifications": "Notifications",
    "CalendarCreated": "CalendarCreated",
    "NoAction": "NoAction",
    "NeedsReview": "NeedsReview",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    agent_data_dir: Path = Field(default=Path("./data"), validation_alias="AGENT_DATA_DIR")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    poll_seconds: int = Field(default=60, validation_alias="POLL_SECONDS")

    tz: str = Field(default="UTC", validation_alias="TZ")

    imap_host: str = Field(validation_alias="IMAP_HOST")
    imap_port: int = Field(default=993, validation_alias="IMAP_PORT")
    imap_username: str = Field(validation_alias="IMAP_USERNAME")
    imap_password: str = Field(validation_alias="IMAP_PASSWORD")

    imap_folder_inbox: str = Field(default="INBOX", validation_alias="IMAP_FOLDER_INBOX")
    imap_drafts_folder: str = Field(default="Drafts", validation_alias="IMAP_DRAFTS_FOLDER")
    imap_sent_folder: str | None = Field(default=None, validation_alias="IMAP_SENT_FOLDER")
    imap_replied_folder: str = Field(default="Replied", validation_alias="IMAP_REPLIED_FOLDER")
    imap_initial_lookback_days: int = Field(
        default=14, validation_alias="IMAP_INITIAL_LOOKBACK_DAYS"
    )
    imap_skip_answered: bool = Field(default=True, validation_alias="IMAP_SKIP_ANSWERED")
    deadline_regex_fallback: bool = Field(
        default=False, validation_alias="DEADLINE_REGEX_FALLBACK"
    )

    imap_filing_mode: Literal["move", "copy"] = Field(
        default="move", validation_alias="IMAP_FILING_MODE"
    )
    imap_create_folders_on_startup: bool = Field(
        default=True, validation_alias="IMAP_CREATE_FOLDERS_ON_STARTUP"
    )

    imap_classification_folders_json: str | None = Field(
        default=None, validation_alias="IMAP_CLASSIFICATION_FOLDERS_JSON"
    )
    imap_classification_confidence_threshold: float = Field(
        default=0.75, validation_alias="IMAP_CLASSIFICATION_CONFIDENCE_THRESHOLD"
    )

    imap_mailbox_prefix: str | None = Field(default=None, validation_alias="IMAP_MAILBOX_PREFIX")

    vip_senders_json: str | None = Field(default=None, validation_alias="VIP_SENDERS_JSON")

    executive_brief_enabled: bool = Field(default=True, validation_alias="EXECUTIVE_BRIEF_ENABLED")
    executive_brief_time_local: str = Field(
        default="07:30", validation_alias="EXECUTIVE_BRIEF_TIME_LOCAL"
    )
    executive_brief_lookback_hours: int = Field(
        default=24, validation_alias="EXECUTIVE_BRIEF_LOOKBACK_HOURS"
    )
    executive_brief_to: str | None = Field(default=None, validation_alias="EXECUTIVE_BRIEF_TO")
    executive_brief_subject_prefix: str = Field(
        default="[Executive Brief]", validation_alias="EXECUTIVE_BRIEF_SUBJECT_PREFIX"
    )

    daily_recap_enabled: bool = Field(default=True, validation_alias="DAILY_RECAP_ENABLED")
    daily_recap_time_local: str = Field(default="18:00", validation_alias="DAILY_RECAP_TIME_LOCAL")
    daily_recap_lookback_hours: int = Field(
        default=24, validation_alias="DAILY_RECAP_LOOKBACK_HOURS"
    )
    daily_recap_to: str | None = Field(default=None, validation_alias="DAILY_RECAP_TO")
    daily_recap_subject_prefix: str = Field(
        default="[Daily Recap]", validation_alias="DAILY_RECAP_SUBJECT_PREFIX"
    )

    weekly_recap_enabled: bool = Field(default=True, validation_alias="WEEKLY_RECAP_ENABLED")
    weekly_recap_day_local: str = Field(default="Mon", validation_alias="WEEKLY_RECAP_DAY_LOCAL")
    weekly_recap_time_local: str = Field(
        default="08:00", validation_alias="WEEKLY_RECAP_TIME_LOCAL"
    )
    weekly_recap_lookback_days: int = Field(
        default=7, validation_alias="WEEKLY_RECAP_LOOKBACK_DAYS"
    )
    weekly_recap_to: str | None = Field(default=None, validation_alias="WEEKLY_RECAP_TO")
    weekly_recap_subject_prefix: str = Field(
        default="[Weekly Recap]", validation_alias="WEEKLY_RECAP_SUBJECT_PREFIX"
    )

    replied_digest_enabled: bool = Field(default=True, validation_alias="REPLIED_DIGEST_ENABLED")
    # Reply digest scheduling: interval-based (hourly by default).
    replied_digest_interval_minutes: int = Field(
        default=60, validation_alias="REPLIED_DIGEST_INTERVAL_MINUTES"
    )
    replied_digest_lookback_minutes: int = Field(
        default=60, validation_alias="REPLIED_DIGEST_LOOKBACK_MINUTES"
    )
    # Backward compatible, no longer used for scheduling but kept to avoid breaking existing envs.
    replied_digest_time_local: str = Field(
        default="18:15", validation_alias="REPLIED_DIGEST_TIME_LOCAL"
    )
    replied_digest_to: str | None = Field(default=None, validation_alias="REPLIED_DIGEST_TO")
    replied_digest_subject_prefix: str = Field(
        default="[Reply Digest]", validation_alias="REPLIED_DIGEST_SUBJECT_PREFIX"
    )

    openrouter_api_key: str | None = Field(default=None, validation_alias="OPENROUTER_API_KEY")
    openrouter_model: str | None = Field(default=None, validation_alias="OPENROUTER_MODEL")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", validation_alias="OPENROUTER_BASE_URL"
    )

    google_oauth_client_secret_json: str | None = Field(
        default=None, validation_alias="GOOGLE_OAUTH_CLIENT_SECRET_JSON"
    )
    google_calendar_id: str = Field(default="primary", validation_alias="GOOGLE_CALENDAR_ID")
    parser_debug: bool = Field(default=False, validation_alias="PARSER_DEBUG")

    @property
    def database_path(self) -> Path:
        return self.agent_data_dir / "agent_state.db"

    @property
    def google_token_path(self) -> Path:
        return self.agent_data_dir / "google_token.json"

    @property
    def vip_senders(self) -> list[str]:
        return list(_loads_json(self.vip_senders_json, default=[]))

    @property
    def classification_folders(self) -> dict[str, str]:
        raw = _loads_json(
            self.imap_classification_folders_json,
            default=DEFAULT_CLASSIFICATION_FOLDERS,
        )
        if not isinstance(raw, dict):
            raise ValueError(
                "IMAP_CLASSIFICATION_FOLDERS_JSON must be a JSON object mapping category->folder"
            )
        return {str(k): str(v) for k, v in raw.items()}

    @property
    def all_required_folders(self) -> list[str]:
        folders = set(self.classification_folders.values())
        folders.add(self.imap_drafts_folder)
        if self.imap_replied_folder:
            folders.add(self.imap_replied_folder)
        return sorted(folders)
