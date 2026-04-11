from langgraph.graph import StateGraph, END
from agents.state import NexusState
from agents.sentinel import sentinel_agent
from agents.maven import maven_agent
from agents.healer import healer_agent
from agents.watcher import watcher_agent
from config import MIN_CONFIDENCE_THRESHOLD, MAX_ITERATIONS


def should_retry(state: NexusState) -> str:
    """
    Conditional edge after Maven:
    - If confidence is below threshold AND we haven't exceeded max retries → retry Maven
    - Otherwise → proceed to Healer
    """
    confidence = state.get("confidence_diagnose", 0.0)
    iterations = state.get("iteration_count", 0)

    if confidence < MIN_CONFIDENCE_THRESHOLD and iterations < MAX_ITERATIONS:
        return "retry_maven"
    return "proceed_to_healer"


def build_graph():
    """
    Builds the LangGraph StateGraph that wires the 4 agents together:

        Sentinel → Maven ←(retry loop)→ Maven → Healer → Watcher → END

    The conditional edge between Maven and Healer re-queries Maven
    when diagnosis confidence is too low, up to MAX_ITERATIONS times.
    """
    graph = StateGraph(NexusState)

    # Add nodes (one per agent)
    graph.add_node("sentinel", sentinel_agent)
    graph.add_node("maven", maven_agent)
    graph.add_node("healer", healer_agent)
    graph.add_node("watcher", watcher_agent)

    # Set entry point
    graph.set_entry_point("sentinel")

    # Linear edge: Sentinel → Maven
    graph.add_edge("sentinel", "maven")

    # Conditional edge: Maven → (retry or proceed)
    graph.add_conditional_edges(
        "maven",
        should_retry,
        {
            "retry_maven": "maven",         # Loop back if confidence low
            "proceed_to_healer": "healer",   # Continue if confidence OK
        },
    )

    # Linear edges: Healer → Watcher → END
    graph.add_edge("healer", "watcher")
    graph.add_edge("watcher", END)

    return graph.compile()


# Singleton — import this in API and Telegram bot
nexus_graph = build_graph()
