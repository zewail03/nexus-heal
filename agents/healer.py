import json
from langchain_groq import ChatGroq
from agents.state import NexusState
from config import GROQ_API_KEY, LLM_MODEL


def healer_agent(state: NexusState) -> dict:
    """
    Agent 3 — Healer: Generates actionable fix plan from diagnosis.
    Extracts commands from runbooks + LLM reasoning.

    Input:  diagnosis, root_cause, retrieved_docs, alert_type
    Output: fix_plan, fix_commands, rollback_plan, estimated_time, human_approved, execution_status
    """
    llm = ChatGroq(
        model=LLM_MODEL,
        temperature=0.2,
        api_key=GROQ_API_KEY,
    )

    # Build context from retrieved docs
    doc_context = "\n\n---\n\n".join(
        [d["content"] for d in state.get("retrieved_docs", [])]
    )

    prompt = f"""You are an expert SRE generating a remediation plan.

ALERT TYPE: {state['alert_type']}
ROOT CAUSE: {state['root_cause']}
DIAGNOSIS: {state['diagnosis']}

RELEVANT RUNBOOKS:
{doc_context}

Generate a complete fix plan. Respond in JSON only (no markdown, no extra text):
{{
    "fix_plan": ["Step 1: ...", "Step 2: ...", "Step 3: ..."],
    "fix_commands": ["command1", "command2", "command3"],
    "rollback_plan": "If the fix fails, do ...",
    "estimated_time": "X minutes"
}}

Rules:
- fix_plan: 3-5 human-readable steps
- fix_commands: actual shell / kubectl / systemctl commands that would fix the issue
- rollback_plan: a short description of how to revert if the fix fails
- estimated_time: realistic estimate like "5 minutes" or "15 minutes"
"""

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
            "fix_plan": [
                "Step 1: Investigate the root cause manually",
                "Step 2: Apply standard remediation from runbook",
                "Step 3: Validate the fix and monitor",
            ],
            "fix_commands": ["echo 'Manual investigation required'"],
            "rollback_plan": "Revert recent changes and escalate to senior engineer",
            "estimated_time": "10 minutes",
        }

    return {
        "fix_plan": parsed.get("fix_plan", []),
        "fix_commands": parsed.get("fix_commands", []),
        "rollback_plan": parsed.get("rollback_plan", "Escalate to senior engineer"),
        "estimated_time": parsed.get("estimated_time", "5 minutes"),
        "human_approved": False,
        "execution_status": "pending",
    }
