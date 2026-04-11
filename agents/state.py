from typing import TypedDict, Optional, List


class NexusState(TypedDict):
    # Input
    alert_id: str
    alert_raw: str           # Raw alert text from monitoring system
    alert_severity: str      # LOW / MEDIUM / HIGH / CRITICAL

    # Sentinel output
    alert_type: str          # cpu_spike / db_connection / disk_full / etc.
    alert_category: str      # infrastructure / application / network / security
    confidence_classify: float

    # Maven output
    retrieved_docs: List[dict]       # List of {doc_id, content, score}
    diagnosis: str                   # LLM diagnosis text
    root_cause: str                  # Short root cause string
    confidence_diagnose: float
    similar_incidents: List[str]     # Past incident IDs

    # Healer output
    fix_plan: List[str]      # Step-by-step fix instructions
    fix_commands: List[str]  # Actual shell/kubectl commands
    rollback_plan: str       # What to do if fix fails
    estimated_time: str      # "5 minutes"

    # Watcher output
    human_approved: bool
    execution_status: str    # pending / approved / rejected / executed / failed
    validation_result: str
    final_message: str       # What to send back to Telegram/UI

    # Meta
    iteration_count: int     # For retry loop tracking
    error: Optional[str]
