from __future__ import annotations

import logging
from typing import Any

from ..deps import Deps

logger = logging.getLogger(__name__)


def file_email_node(state: dict[str, Any], deps: Deps) -> dict[str, Any]:
    actions = state["actions"]
    if not actions.file_email:
        return state
    meta = state["meta"]
    dest = state["filing_folder"]
    if deps.settings.imap_create_folders_on_startup:
        deps.imap.ensure_mailbox(dest)
    if deps.settings.imap_filing_mode == "copy":
        deps.imap.copy(meta.uid, dest_mailbox=dest)
        deps.store.set_filing_result(meta.folder, meta.uid, filing_folder=dest, status="copied")
        logger.info(
            "Email copied",
            extra={
                "event": "email_copied",
                "email_uid": meta.uid,
                "email_folder": meta.folder,
                "dest_folder": dest,
            },
        )
        next_state = dict(state)
        next_state.update({"filed_folder": dest, "filing_status": "copied"})
        return next_state
    deps.imap.move(meta.uid, dest_mailbox=dest)
    deps.store.set_filing_result(meta.folder, meta.uid, filing_folder=dest, status="moved")
    logger.info(
        "Email moved",
        extra={
            "event": "email_moved",
            "email_uid": meta.uid,
            "email_folder": meta.folder,
            "dest_folder": dest,
        },
    )
    next_state = dict(state)
    next_state.update({"filed_folder": dest, "filing_status": "moved"})
    return next_state
