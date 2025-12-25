from __future__ import annotations

from langgraph.graph import END, StateGraph

from .deps import Deps
from .nodes.classify_email import classify_email_node
from .nodes.create_calendar_event import create_calendar_event_node
from .nodes.decide_actions import decide_actions_node
from .nodes.draft_reply import draft_reply_node
from .nodes.extract_event import extract_event_node
from .nodes.file_email import file_email_node
from .nodes.persist_state import persist_state_node
from .nodes.priority_score import priority_score_node
from .nodes.validate_event import validate_event_node


def build_email_graph(deps: Deps):  # type: ignore[no-untyped-def]
    graph = StateGraph(dict)  # type: ignore[type-var]

    graph.add_node("priority", lambda s: priority_score_node(s, deps))
    graph.add_node("classify", lambda s: classify_email_node(s, deps))
    graph.add_node("decide", lambda s: decide_actions_node(s, deps))
    graph.add_node("draft", lambda s: draft_reply_node(s, deps))
    graph.add_node("extract_event", lambda s: extract_event_node(s, deps))
    graph.add_node("validate_event", lambda s: validate_event_node(s, deps))
    graph.add_node("create_calendar", lambda s: create_calendar_event_node(s, deps))
    graph.add_node("file", lambda s: file_email_node(s, deps))
    graph.add_node("persist", lambda s: persist_state_node(s, deps))

    graph.set_entry_point("priority")
    graph.add_edge("priority", "classify")
    graph.add_edge("classify", "decide")
    graph.add_edge("decide", "draft")
    graph.add_edge("draft", "extract_event")
    graph.add_edge("extract_event", "validate_event")
    graph.add_edge("validate_event", "create_calendar")
    graph.add_edge("create_calendar", "file")
    graph.add_edge("file", "persist")
    graph.add_edge("persist", END)

    return graph.compile()
