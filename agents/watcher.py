from agents.state import NexusState


def watcher_agent(state: NexusState) -> dict:
    """
    Agent 4 — Watcher: Post-fix validation agent.
    If approved:  marks as executed, sends success message.
    If rejected:  marks as escalated, sends escalation message.

    Input:  human_approved, fix_plan, execution_status
    Output: validation_result, final_message, execution_status
    """
    if state.get("human_approved", False):
        # Simulate fix execution
        # In a real system this would: run the fix_commands, check exit codes,
        # poll monitoring endpoints, and verify the alert has cleared.
        fix_summary = "\n".join(
            f"  {i+1}. {step}" for i, step in enumerate(state.get("fix_plan", []))
        )

        return {
            "execution_status": "executed",
            "validation_result": "Fix applied successfully. All checks passed.",
            "final_message": (
                f"\u2705 RESOLVED: {state.get('root_cause', 'Unknown')}\n\n"
                f"Fix applied:\n{fix_summary}\n\n"
                f"Estimated recovery time: {state.get('estimated_time', 'N/A')}"
            ),
        }
    else:
        return {
            "execution_status": "rejected",
            "validation_result": "Fix was rejected by operator. Escalating.",
            "final_message": (
                "\u26a0\ufe0f Escalated to senior engineer.\n\n"
                f"Alert type: {state.get('alert_type', 'Unknown')}\n"
                f"Root cause: {state.get('root_cause', 'Unknown')}\n"
                f"Diagnosis: {state.get('diagnosis', 'N/A')}"
            ),
        }
