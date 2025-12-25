from __future__ import annotations

import logging
from typing import Any

from ..deps import Deps

logger = logging.getLogger(__name__)


def create_calendar_event_node(state: dict[str, Any], deps: Deps) -> dict[str, Any]:
    actions = state["actions"]
    if not actions.create_calendar_event:
        return state
    meta = state["meta"]
    existing = deps.store.get_message_calendar_event_id(meta.folder, meta.uid)
    if existing:
        next_state = dict(state)
        next_state.update({"calendar_event_id": existing})
        return next_state
    event = state.get("validated_event")
    if not event:
        return state
    if deps.calendar is None:
        logger.info(
            "Calendar not configured, skipping event creation",
            extra={"event": "calendar_not_configured", "email_uid": meta.uid},
        )
        return state
    context_lines = []
    if meta.subject:
        context_lines.append(f"Subject: {meta.subject}")
    if meta.from_addr:
        context_lines.append(f"From: {meta.from_addr}")
    if meta.date:
        context_lines.append(f"Date: {meta.date}")
    if meta.message_id:
        context_lines.append(f"Email Message-ID: {meta.message_id}")
    description_extra = "\n".join(context_lines)
    try:
        event_id = deps.calendar.create_event(
            event,
            description_extra=description_extra,
        )
    except Exception:
        logger.exception(
            "Calendar event creation failed",
            extra={"event": "calendar_event_failed", "email_uid": meta.uid},
        )
        return state
    deps.store.set_calendar_event_id(meta.folder, meta.uid, event_id)
    logger.info(
        "Calendar event created",
        extra={
            "event": "calendar_event_created",
            "email_uid": meta.uid,
            "email_folder": meta.folder,
        },
    )
    next_state = dict(state)
    next_state.update({"calendar_event_id": event_id})
    return next_state
