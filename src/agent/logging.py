from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

REDACT_KEYS = ("password", "secret", "api_key", "token", "authorization")


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if any(p in k.lower() for p in REDACT_KEYS):
                out[k] = "***"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # Extract all extra fields passed via logger.info(..., extra={...})
        for key in (
            "event",
            "email_uid",
            "email_folder",
            "dest_folder",
            "message_id",
            "imap_fetch",
            "calendar_invite_detected",
            "meeting_links_found",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(_redact(payload), ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
