from __future__ import annotations

import logging
import re
from typing import Any

from ..deps import Deps
from ..llm_openrouter import decide_actions
from ..models import ClassificationCategory

logger = logging.getLogger(__name__)

_DEADLINE_KEYWORDS = (
    "deadline",
    "due",
    "by",
    "before",
    "entro",
    "scadenza",
    "termine",
    "da consegnare",
    "da inviare",
)
_DATE_PATTERNS = [
    re.compile(r"\b\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?\b"),
    re.compile(r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b"),
    re.compile(
        r"\b("
        r"jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|"
        r"aug|august|sep|sept|september|oct|october|nov|november|dec|december|"
        r"gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|"
        r"ottobre|novembre|dicembre"
        r")\b"
    ),
]


def _deadline_signals(text: str) -> tuple[bool, bool]:
    lowered = text.lower()
    keyword_hit = any(keyword in lowered for keyword in _DEADLINE_KEYWORDS)
    date_hit = any(pattern.search(lowered) for pattern in _DATE_PATTERNS)
    return keyword_hit, date_hit


def _looks_like_deadline(text: str) -> bool:
    keyword_hit, date_hit = _deadline_signals(text)
    if not keyword_hit:
        return False
    return date_hit


def decide_actions_node(state: dict[str, Any], deps: Deps) -> dict[str, Any]:
    classification = state["classification"]
    if classification.confidence < deps.settings.imap_classification_confidence_threshold:
        classification.category = ClassificationCategory.NeedsReview
    actions = decide_actions(classification)
    text = state.get("text", "")
    keyword_hit = False
    date_hit = False
    if deps.settings.deadline_regex_fallback or deps.settings.parser_debug:
        keyword_hit, date_hit = _deadline_signals(text)
        logger.debug(
            "Deadline heuristic signals",
            extra={
                "event": "deadline_signals",
                "email_uid": getattr(state.get("meta"), "uid", None),
                "email_folder": getattr(state.get("meta"), "folder", None),
                "extra": {
                    "keyword_hit": keyword_hit,
                    "date_hit": date_hit,
                    "text_length": len(text),
                },
            },
        )
    if (
        deps.settings.deadline_regex_fallback
        and (not actions.extract_event)
        and keyword_hit
        and date_hit
    ):
        actions.extract_event = True
        actions.create_calendar_event = True
        logger.info(
            "Deadline heuristic forced event extraction",
            extra={
                "event": "deadline_override",
                "email_uid": getattr(state.get("meta"), "uid", None),
                "email_folder": getattr(state.get("meta"), "folder", None),
            },
        )
    filing_folder = deps.settings.classification_folders.get(
        classification.category.value,
        "NeedsReview",
    )
    next_state = dict(state)
    next_state.update(
        {
            "actions": actions,
            "filing_folder": filing_folder,
            "classification": classification,
        }
    )
    return next_state
