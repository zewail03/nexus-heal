import json
from langchain_groq import ChatGroq
from rag.hybrid_retriever import hybrid_retrieve as retrieve_docs
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

    # Build RAG match quality hint for confidence calibration
    rag_scores = [d.get("score", 0) for d in docs]
    avg_rag_score = sum(rag_scores) / len(rag_scores) if rag_scores else 0

    prompt = f"""You are an expert SRE diagnosing an infrastructure incident.

ALERT: {state['alert_raw']}
TYPE: {state['alert_type']}
SEVERITY: {state['alert_severity']}

RELEVANT RUNBOOKS:
{context}

Base your diagnosis ONLY on the alert and the runbooks above. Do not mention
similarity scores, retrieval quality, or any metadata — only facts from the runbooks.

Based on the alert and the runbooks above, provide:
1. Root cause (one sentence)
2. Detailed diagnosis (2-3 sentences)
3. Confidence score (0.0-1.0) — calibrate this carefully:
   - 0.9-1.0: Alert exactly matches a known runbook pattern, root cause is obvious
   - 0.7-0.8: Alert mostly matches a runbook, high certainty but some ambiguity
   - 0.5-0.6: Alert partially matches, diagnosis is a best guess
   - 0.3-0.4: Alert is vague or matches multiple possible causes
   - 0.1-0.2: Almost no match, diagnosis is speculative
   Consider: how specific is the alert? How well do the runbooks match? Are there multiple possible root causes?
4. Similar past incidents mentioned in the runbooks (list of short descriptions, or empty list if none match)

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

    # Calibrate confidence using RAG scores + LLM confidence + alert length
    llm_confidence = float(parsed.get("confidence", 0.5))

    # Factor 1: RAG retrieval quality (how well runbooks matched)
    rag_factor = min(avg_rag_score, 1.0)

    # Factor 2: Alert specificity (longer, more detailed alerts = higher confidence)
    alert_len = len(state.get("alert_raw", ""))
    specificity_factor = min(alert_len / 120.0, 1.0)  # caps at 120 chars

    # Blend: 40% LLM, 35% RAG quality, 25% alert specificity
    calibrated_confidence = round(
        0.40 * llm_confidence + 0.35 * rag_factor + 0.25 * specificity_factor, 2
    )
    # Clamp to [0.1, 0.98]
    calibrated_confidence = max(0.1, min(0.98, calibrated_confidence))

    # Increment iteration count for retry logic
    iteration_count = state.get("iteration_count", 0) + 1

    return {
        "retrieved_docs": docs,
        "diagnosis": parsed.get("diagnosis", "No diagnosis available"),
        "root_cause": parsed.get("root_cause", "Unknown"),
        "confidence_diagnose": calibrated_confidence,
        "similar_incidents": parsed.get("similar_incidents", []),
        "iteration_count": iteration_count,
    }
