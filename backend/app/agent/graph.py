from langgraph.graph import StateGraph, END
from app.agent.state import BiographerState
from app.agent.nodes.receive import receive
from app.agent.nodes.classify import classify
from app.agent.nodes.correct import correct
from app.agent.nodes.strategize import strategize
from app.agent.nodes.respond import respond
from app.agent.nodes.extract import extract
from app.agent.nodes.finalize import finalize


def _route_after_classify(state: BiographerState) -> str:
    """Route based on classification results."""
    intent = state.get("intent", "sharing")
    if intent == "correcting":
        return "correct"
    elif intent == "greeting":
        # Future: route to GREET node
        return "strategize"
    else:
        return "strategize"


def _route_after_respond(state: BiographerState) -> str:
    """Route based on whether we should extract."""
    if state.get("should_extract", True):
        return "extract"
    return "finalize"


def build_graph() -> StateGraph:
    """Build the agent graph: RECEIVE → CLASSIFY → STRATEGIZE → RESPOND → EXTRACT/FINALIZE.

    Note: For streaming, chat.py manually orchestrates these nodes instead of using
    the compiled graph, because LangGraph's streaming support requires special handling.
    This graph serves as the canonical architecture definition and for non-streaming use.
    """
    graph = StateGraph(BiographerState)

    graph.add_node("receive", receive)
    graph.add_node("classify", classify)
    graph.add_node("correct", correct)
    graph.add_node("strategize", strategize)
    graph.add_node("respond", respond)
    graph.add_node("extract", extract)
    graph.add_node("finalize", finalize)

    graph.set_entry_point("receive")
    graph.add_edge("receive", "classify")
    graph.add_conditional_edges("classify", _route_after_classify)
    graph.add_edge("correct", "strategize")
    graph.add_edge("strategize", "respond")
    graph.add_conditional_edges("respond", _route_after_respond)
    graph.add_edge("extract", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


# Compiled graph singleton
agent_graph = build_graph()
