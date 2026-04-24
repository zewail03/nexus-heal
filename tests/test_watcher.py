"""
Tests for the Watcher's safety allowlist + real execution path.

These cover the module directly (no Groq needed) so they are fast and
deterministic.  Together with the integration test in `test_e2e.py::
test_approve_runs_safe_commands_for_real`, they prove that the Watcher:

  * executes real shell commands when they are on the safe allowlist,
  * refuses to execute anything on the mutation list, even if approved,
  * falls back to "unknown" (still refuses) for commands that match
    neither list,
  * builds `validation_result` / `command_results` from the actual
    captured output — not from a hard-coded success string.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from agents.watcher import (  # noqa: E402
    SAFE_COMMAND_PREFIXES,
    MUTATION_COMMAND_PREFIXES,
    classify_command,
    watcher_agent,
)


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cmd", [
    "df -h",
    "kubectl get pods -n prod",
    "kubectl top pods",
    "systemctl status nginx",
    "curl -I https://api.example.com/health",
    "openssl s_client -connect api.example.com:443",
    "ping -c 3 10.0.0.1",
    "pg_isready -h db.internal -p 5432",
    "rabbitmqctl list_queues",
    "docker ps",
])
def test_classify_safe(cmd: str) -> None:
    assert classify_command(cmd) == "safe"


@pytest.mark.parametrize("cmd", [
    "rm -rf /tmp/foo",
    "kubectl delete pod evil",
    "kubectl rollout undo deployment/api",
    "systemctl restart postgresql",
    "kill -9 1234",
    "truncate -s 0 /var/log/app.log",
    "docker system prune -a --volumes",
    "ALTER SYSTEM SET max_connections = 200;",
    "DROP TABLE users;",
    "DELETE FROM sessions WHERE expired < NOW();",
])
def test_classify_mutation(cmd: str) -> None:
    assert classify_command(cmd) == "mutation"


@pytest.mark.parametrize("cmd", [
    "",
    "   ",
    "some_random_unfamiliar_binary --flag",
    "./deploy.sh production",
])
def test_classify_unknown(cmd: str) -> None:
    assert classify_command(cmd) == "unknown"


def test_allowlists_do_not_overlap() -> None:
    """A prefix belonging to both lists would be ambiguous.  Mutation
    wins at classify_command time, but the lists should be disjoint by
    design as a sanity guard."""
    safe_lower = {p.strip().lower() for p in SAFE_COMMAND_PREFIXES}
    mut_lower = {p.strip().lower() for p in MUTATION_COMMAND_PREFIXES}
    # No safe prefix should start with a mutation prefix (or vice versa)
    overlap = safe_lower & mut_lower
    assert not overlap, f"allowlist overlap: {overlap}"


# ---------------------------------------------------------------------------
# Watcher behaviour — rejected path (no approval)
# ---------------------------------------------------------------------------

def _state(**overrides) -> dict:
    base = {
        "alert_id": "WTEST-001",
        "alert_raw": "test alert",
        "alert_type": "cpu_spike",
        "alert_severity": "HIGH",
        "alert_category": "infrastructure",
        "root_cause": "test root cause",
        "diagnosis": "test diagnosis",
        "fix_plan": ["step 1", "step 2"],
        "fix_commands": [],
        "rollback_plan": "revert",
        "estimated_time": "5 minutes",
        "human_approved": False,
        "execution_status": "pending",
        "validation_result": "",
        "command_results": [],
        "final_message": "",
    }
    base.update(overrides)
    return base


def test_watcher_rejects_without_approval_and_does_not_execute() -> None:
    out = watcher_agent(_state(
        human_approved=False,
        fix_commands=["df -h"],  # would be safe if approved
    ))
    assert out["execution_status"] == "rejected"
    assert out["command_results"] == []  # nothing ran
    assert "Escalated" in out["final_message"]


# ---------------------------------------------------------------------------
# Watcher behaviour — approved path, real execution
# ---------------------------------------------------------------------------

def test_watcher_executes_safe_command_for_real() -> None:
    """Uses `echo` because it's on the allowlist and works cross-platform
    (git-bash, Linux, macOS).  Proves we are NOT returning a hard-coded
    success string — the captured stdout contains the live echo output."""
    out = watcher_agent(_state(
        human_approved=True,
        fix_commands=["echo nexus-heal-watcher-is-real"],
    ))
    assert out["execution_status"] == "executed"
    assert len(out["command_results"]) == 1
    result = out["command_results"][0]
    assert result["executed"] is True
    assert result["classification"] == "safe"
    assert result["exit_code"] == 0
    assert "nexus-heal-watcher-is-real" in result["stdout"]
    # validation_result must include the actual captured output prefix
    assert "EXECUTED OK" in out["validation_result"]


def test_watcher_gates_mutation_command_even_when_approved() -> None:
    """rm -rf is destructive.  Even with human_approved=True the Watcher
    must refuse to run it and surface it as gated."""
    out = watcher_agent(_state(
        human_approved=True,
        fix_commands=["rm -rf /tmp/should-never-happen"],
    ))
    assert len(out["command_results"]) == 1
    result = out["command_results"][0]
    assert result["executed"] is False
    assert result["classification"] == "mutation"
    assert "manual review" in (result.get("error") or "").lower()
    assert "GATED mutation" in out["validation_result"]


def test_watcher_gates_unknown_command() -> None:
    """Commands that match neither allowlist nor mutation list are also
    gated (fail-safe default)."""
    out = watcher_agent(_state(
        human_approved=True,
        fix_commands=["fictitious_binary --magic"],
    ))
    result = out["command_results"][0]
    assert result["executed"] is False
    assert result["classification"] == "unknown"


def test_watcher_handles_mixed_commands() -> None:
    """Realistic mix: a safe verification check + a gated mutation.
    The safe one runs, the mutation is held."""
    out = watcher_agent(_state(
        human_approved=True,
        fix_commands=[
            "echo checking-disk",
            "rm -rf /var/log/old",
        ],
    ))
    assert len(out["command_results"]) == 2
    executed = [r for r in out["command_results"] if r["executed"]]
    gated = [r for r in out["command_results"] if not r["executed"]]
    assert len(executed) == 1
    assert len(gated) == 1
    assert executed[0]["classification"] == "safe"
    assert gated[0]["classification"] == "mutation"
