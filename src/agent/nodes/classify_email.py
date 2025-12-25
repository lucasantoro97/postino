from __future__ import annotations

import json
from typing import Any

from ..deps import Deps


def classify_email_node(state: dict[str, Any], deps: Deps) -> dict[str, Any]:
    meta = state["meta"]
    text = state["text"]
    classification = deps.llm.classify(meta=meta, text=text)
    next_state = dict(state)
    next_state.update(
        {
            "classification": classification,
            "classification_tags_json": json.dumps(classification.tags),
        }
    )
    return next_state
