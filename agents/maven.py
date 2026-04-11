import json
from langchain_groq import ChatGroq
from rag.retriever import retrieve_docs
from agents.state import NexusState
from config import GROQ_API_KEY, LLM_MODEL, LLM_TEMPERATURE, RAG_TOP_K


def maven_agent(state: NexusState) -> dict:
    """
    Agent 2 — Maven: RAG-powered diagnosis agent.
    1. Queries ChromaDB with alert text
    2. Retrieves top-k most relevant runbooks
    3. Sends alert + docs to LLM for diagnosis

    Input:  alert_type, alert_raw, alert_severity
    Output: retrieved_docs, diagnosis, root_cause, confidence_diagnose, similar_incidents
    """
    # Step 1: RAG retrieval
    docs = retrieve_docs(
        query=state["alert_raw"],
        alert_type=state["alert_type"],
        top_k=RAG_TOP_K,
    )

    # Step 2: LLM diagnosis with retrieved context
    llm = ChatGroq(
        model=LLM_MODEL,
        temperature=LLM_TEMPERATURE,
        api_key=GROQ_API_KEY,
    )

    context = "\n\n---\n\n".join([d["content"] for d in docs])

    prompt = f"""You are an expert SRE diagnosing an infrastructure incident.

ALERT: {state['alert_raw']}
TYPE: {state['alert_type']}
SEVERITY: {state['alert_severity']}

RELEVANT RUNBOOKS:
{context}

Based on the alert and the runbooks above, provide:
1. Root cause (one sentence)
2. Detailed diagnosis (2-3 sentences)
3. Confidence score (0.0-1.0) — how sure you are about this diagnosis
4. Similar past incidents mentioned in the runbooks (list of short descriptions)

Respond in JSON only (no markdown, no extra text):
{{"root_cause": "...", "diagnosis": "...", "confidence": 0.0, "similar_incidents": ["...", "..."]}}"""

    response = llm.invoke(prompt)
    content = response.content.strip()

    # Strip markdown code fences if present
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = {
            "root_cause": "Unable to determine root cause — LLM parse error",
            "diagnosis": "The alert requires manual investigation. Automated diagnosis could not parse LLM output.",
            "confidence": 0.3,
            "similar_incidents": [],
        }

    # Increment iteration count for retry logic
    iteration_count = state.get("iteration_count", 0) + 1

    return {
        "retrieved_docs": docs,
        "diagnosis": parsed.get("diagnosis", "No diagnosis available"),
        "root_cause": parsed.get("root_cause", "Unknown"),
        "confidence_diagnose": float(parsed.get("confidence", 0.3)),
        "similar_incidents": parsed.get("similar_incidents", []),
        "iteration_count": iteration_count,
    }
