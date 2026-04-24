from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="NEXUS-HEAL API", version="1.0.0")

# In-memory store for pending alerts (keyed by alert_id)
_pending_alerts: dict = {}


class AlertRequest(BaseModel):
    alert_id: str
    alert_text: str
    source: str = "n8n"  # "n8n" | "telegram" | "manual"


class DiagnosisResponse(BaseModel):
    alert_id: str
    alert_type: str
    severity: str
    root_cause: str
    diagnosis: str
    confidence: float
    fix_plan: list
    fix_commands: list
    rollback_plan: str
    estimated_time: str
    status: str


@app.post("/analyze", response_model=DiagnosisResponse)
async def analyze_alert(request: AlertRequest):
    """
    Main endpoint. n8n / Telegram / manual clients post here.
    Runs the full LangGraph pipeline and returns the diagnosis.
    """
    # Lazy import to avoid circular import at module level
    from graph.pipeline import nexus_graph

    initial_state = {
        "alert_id": request.alert_id,
        "alert_raw": request.alert_text,
        "alert_severity": "",
        "alert_type": "",
        "alert_category": "",
        "confidence_classify": 0.0,
        "retrieved_docs": [],
        "diagnosis": "",
        "root_cause": "",
        "confidence_diagnose": 0.0,
        "similar_incidents": [],
        "fix_plan": [],
        "fix_commands": [],
        "rollback_plan": "",
        "estimated_time": "",
        "human_approved": False,
        "execution_status": "pending",
        "validation_result": "",
        "command_results": [],
        "final_message": "",
        "iteration_count": 0,
        "error": None,
    }

    result = nexus_graph.invoke(initial_state)

    # Store result for later approval
    _pending_alerts[request.alert_id] = result

    return DiagnosisResponse(
        alert_id=result["alert_id"],
        alert_type=result["alert_type"],
        severity=result["alert_severity"],
        root_cause=result["root_cause"],
        diagnosis=result["diagnosis"],
        confidence=result["confidence_diagnose"],
        fix_plan=result["fix_plan"],
        fix_commands=result["fix_commands"],
        rollback_plan=result["rollback_plan"],
        estimated_time=result.get("estimated_time", "5 minutes"),
        status=result["execution_status"],
    )


@app.post("/approve/{alert_id}")
async def approve_fix(alert_id: str, approved: bool = True):
    """
    Endpoint for Telegram bot / UI to call when user taps Approve/Reject.
    Updates state and triggers the Watcher agent.
    """
    from agents.watcher import watcher_agent

    stored = _pending_alerts.get(alert_id)
    if not stored:
        return {"error": f"Alert {alert_id} not found"}

    # Update approval and re-run watcher
    stored["human_approved"] = approved
    watcher_result = watcher_agent(stored)
    stored.update(watcher_result)

    return {
        "alert_id": alert_id,
        "approved": approved,
        "execution_status": stored["execution_status"],
        "validation_result": stored.get("validation_result", ""),
        "command_results": stored.get("command_results", []),
        "final_message": stored["final_message"],
    }


@app.get("/alerts")
async def list_alerts():
    """Returns all processed alerts (for Streamlit dashboard)."""
    return {
        alert_id: {
            "alert_id": s["alert_id"],
            "alert_type": s.get("alert_type", ""),
            "severity": s.get("alert_severity", ""),
            "root_cause": s.get("root_cause", ""),
            "diagnosis": s.get("diagnosis", ""),
            "confidence": s.get("confidence_diagnose", 0),
            "status": s.get("execution_status", "pending"),
            "fix_plan": s.get("fix_plan", []),
        }
        for alert_id, s in _pending_alerts.items()
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "nexus-heal"}
