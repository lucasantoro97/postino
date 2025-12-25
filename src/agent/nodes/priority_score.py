from __future__ import annotations

from typing import Any

from ..deps import Deps
from ..priority import compute_priority


def priority_score_node(state: dict[str, Any], deps: Deps) -> dict[str, Any]:
    meta = state["meta"]
    text = state["text"]
    score, tags = compute_priority(meta, text, vip_senders=deps.settings.vip_senders)
    next_state = dict(state)
    next_state.update({"priority": score, "priority_tags": tags})
    return next_state
