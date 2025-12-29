from __future__ import annotations

from unittest.mock import MagicMock

from agent.config import Settings
from agent.deps import Deps
from agent.models import ClassificationCategory, ClassificationResult
from agent.nodes.decide_actions import decide_actions_node


def _build_deps() -> Deps:
    settings = Settings(IMAP_HOST="h", IMAP_USERNAME="me@example.com", IMAP_PASSWORD="x")
    return Deps(
        settings=settings, store=MagicMock(), imap=MagicMock(), llm=MagicMock(), calendar=None
    )


def test_deadline_text_triggers_event_actions() -> None:
    deps = _build_deps()
    classification = ClassificationResult(
        category=ClassificationCategory.ToReply,
        confidence=1.0,
        rationale="",
        reply_needed=False,
        contains_event_request=False,
    )
    state = {"classification": classification, "text": "Please send the report by 12/01/2026."}
    out = decide_actions_node(state, deps)
    assert out["actions"].extract_event is True
    assert out["actions"].create_calendar_event is True


def test_no_deadline_does_not_force_event_actions() -> None:
    deps = _build_deps()
    classification = ClassificationResult(
        category=ClassificationCategory.Notifications,
        confidence=1.0,
        rationale="",
        reply_needed=False,
        contains_event_request=False,
    )
    state = {"classification": classification, "text": "FYI, the report was sent."}
    out = decide_actions_node(state, deps)
    assert out["actions"].extract_event is False
    assert out["actions"].create_calendar_event is False
