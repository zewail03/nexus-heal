import json
from langchain_groq import ChatGroq
from agents.state import NexusState
from config import GROQ_API_KEY, LLM_MODEL

ALERT_TYPES = [
    "cpu_spike", "memory_leak", "disk_full", "db_connection",
    "network_latency", "ssl_expired", "api_timeout",
    "pod_crash", "queue_overflow", "auth_failure"
]


def sentinel_agent(state: NexusState) -> dict:
    """
    Agent 1 — Sentinel: Classifies incoming alert into a known type.
    Uses LLM to parse natural language alerts.

    Input:  alert_raw
    Output: alert_type, alert_severity, alert_category, confidence_classify
    """
    llm = ChatGroq(
        model=LLM_MODEL,
        temperature=0,
        api_key=GROQ_API_KEY,
    )

    prompt = f"""You are an infrastructure alert classifier.

Classify this alert into exactly one type from: {ALERT_TYPES}
Also classify severity: LOW, MEDIUM, HIGH, or CRITICAL
Also classify category: infrastructure, application, network, or security

Alert: {state['alert_raw']}

Respond in JSON only (no markdown, no extra text):
{{"alert_type": "...", "severity": "...", "category": "...", "confidence": 0.0}}

Rules:
- confidence is a float between 0.0 and 1.0, calibrated as follows:
  - 0.9-1.0: Alert clearly mentions exact keywords (e.g., "CPU 98%", "disk full", "SSL expired")
  - 0.7-0.8: Alert strongly implies a type but uses indirect language
  - 0.5-0.6: Alert is ambiguous, could be multiple types
  - 0.3-0.4: Alert is vague with minimal detail
- alert_type MUST be one of the listed types
- severity MUST be one of: LOW, MEDIUM, HIGH, CRITICAL
  - CRITICAL: service down, data loss risk, security breach
  - HIGH: degraded performance, approaching limits
  - MEDIUM: warning signs, not yet impacting users
  - LOW: informational, minor issue
- category MUST be one of: infrastructure, application, network, security"""

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
        # Fallback: best-effort defaults
        parsed = {
            "alert_type": "cpu_spike",
            "severity": "MEDIUM",
            "category": "infrastructure",
            "confidence": 0.5,
        }

    # Validate alert_type
    alert_type = parsed.get("alert_type", "cpu_spike")
    if alert_type not in ALERT_TYPES:
        alert_type = "cpu_spike"

    return {
        "alert_type": alert_type,
        "alert_severity": parsed.get("severity", "MEDIUM"),
        "alert_category": parsed.get("category", "infrastructure"),
        "confidence_classify": float(parsed.get("confidence", 0.5)),
    }
