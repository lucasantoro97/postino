from __future__ import annotations

from typing import Any

from ..deps import Deps
from ..validate_event import validate_event_candidate


def validate_event_node(state: dict[str, Any], deps: Deps) -> dict[str, Any]:
    candidates = state.get("event_candidates") or []
    if not candidates:
        next_state = dict(state)
        next_state.update({"validated_event": None, "event_reject_reason": "no-candidates"})
        return next_state
    res = validate_event_candidate(
        candidates[0],
        default_tz=deps.settings.tz,
        context_text=str(state.get("text") or ""),
    )
    if not res.ok:
        next_state = dict(state)
        next_state.update({"validated_event": None, "event_reject_reason": res.reason})
        return next_state
    next_state = dict(state)
    next_state.update({"validated_event": res.event, "event_reject_reason": None})
    return next_state
