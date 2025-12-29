from __future__ import annotations

import re
from typing import Any

from ..deps import Deps
from ..llm_openrouter import decide_actions
from ..models import ClassificationCategory

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


def _looks_like_deadline(text: str) -> bool:
    lowered = text.lower()
    if not any(keyword in lowered for keyword in _DEADLINE_KEYWORDS):
        return False
    return any(pattern.search(lowered) for pattern in _DATE_PATTERNS)


def decide_actions_node(state: dict[str, Any], deps: Deps) -> dict[str, Any]:
    classification = state["classification"]
    if classification.confidence < deps.settings.imap_classification_confidence_threshold:
        classification.category = ClassificationCategory.NeedsReview
    actions = decide_actions(classification)
    if not actions.extract_event and _looks_like_deadline(state.get("text", "")):
        actions.extract_event = True
        actions.create_calendar_event = True
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
