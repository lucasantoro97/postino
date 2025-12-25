from __future__ import annotations

from typing import Any

from ..deps import Deps


def extract_event_node(state: dict[str, Any], deps: Deps) -> dict[str, Any]:
    actions = state["actions"]
    if not actions.extract_event:
        return state
    meta = state["meta"]
    candidates = deps.llm.extract_events(meta=meta, text=state["text"])
    next_state = dict(state)
    next_state.update({"event_candidates": candidates})
    return next_state
