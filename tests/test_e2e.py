"""
End-to-end smoke test for the full NEXUS-HEAL pipeline.

Covers two layers:

1. HTTP layer — posts four seeded alerts through the FastAPI `/analyze`
   endpoint via `fastapi.testclient.TestClient` and asserts the response
   contract.
2. Graph layer — invokes `nexus_graph` directly on one seeded alert to
   inspect fields that the HTTP response does not surface (notably
   `retrieved_docs`, which is internal state).

Running these tests requires a valid `GROQ_API_KEY` in the environment; the
fixture in `conftest.py` skips the suite if the key is missing so CI doesn't
silently pretend to pass.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.server import app
from graph.pipeline import nexus_graph


# ---------------------------------------------------------------------------
# Seeded alerts — four distinct runbook categories so we exercise breadth
# ---------------------------------------------------------------------------

SEEDED_ALERTS = [
    ("E2E-CPU-001", "CPU usage 98% on api-gateway, OOM errors in logs"),
    ("E2E-DB-001",  "Database connection pool exhausted, 503 errors on /api/users"),
    ("E2E-SSL-001", "SSL certificate expired on api.example.com"),
    ("E2E-POD-001", "payment-service pod in CrashLoopBackOff, exit code 137"),
]


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# HTTP-layer smoke test — one parameterised test per seeded alert
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("alert_id,alert_text", SEEDED_ALERTS, ids=[a[0] for a in SEEDED_ALERTS])
def test_analyze_endpoint_produces_valid_diagnosis(
    client: TestClient, alert_id: str, alert_text: str
) -> None:
    """The /analyze endpoint should run the full 4-agent pipeline to completion
    and return a populated diagnosis response."""
    resp = client.post(
        "/analyze",
        json={"alert_id": alert_id, "alert_text": alert_text, "source": "pytest"},
    )
    assert resp.status_code == 200, f"status={resp.status_code} body={resp.text}"
    data = resp.json()

    # Echoed input
    assert data["alert_id"] == alert_id

    # Sentinel outputs
    assert isinstance(data["alert_type"], str) and data["alert_type"], \
        "Sentinel failed to classify alert_type"
    assert data["severity"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}, \
        f"severity not in canonical set: {data['severity']!r}"

    # Maven outputs
    assert isinstance(data["root_cause"], str) and data["root_cause"].strip(), \
        "root_cause must be non-empty"
    assert isinstance(data["diagnosis"], str) and data["diagnosis"].strip(), \
        "diagnosis must be non-empty"
    assert isinstance(data["confidence"], (int, float)), \
        f"confidence must be numeric, got {type(data['confidence']).__name__}"
    assert 0.0 <= float(data["confidence"]) <= 1.0, \
        f"confidence out of [0,1]: {data['confidence']}"

    # Healer outputs
    assert isinstance(data["fix_plan"], list) and len(data["fix_plan"]) >= 1, \
        "fix_plan must contain at least one step"
    assert all(isinstance(s, str) and s.strip() for s in data["fix_plan"]), \
        "every fix_plan step must be a non-empty string"
    assert isinstance(data["fix_commands"], list), "fix_commands must be a list"
    assert isinstance(data["rollback_plan"], str) and data["rollback_plan"].strip(), \
        "rollback_plan must be non-empty"

    # The graph runs Sentinel → Maven → Healer → Watcher → END in one pass.
    # Without a human approval the Watcher lands on "rejected" by design.
    # We just assert the pipeline reached a terminal status, proving it ran
    # end-to-end without exception.
    assert data["status"] in {"rejected", "executed", "pending"}, \
        f"unexpected terminal status: {data['status']!r}"


# ---------------------------------------------------------------------------
# Graph-layer smoke test — inspects internal state (retrieved_docs)
# ---------------------------------------------------------------------------

def _initial_state(alert_id: str, alert_text: str) -> dict:
    """Mirror the shape built inside api/server.py::analyze_alert so the
    pipeline sees exactly the same input in both tests."""
    return {
        "alert_id": alert_id,
        "alert_raw": alert_text,
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


def test_approve_endpoint_surfaces_command_results(client: TestClient) -> None:
    """After /approve, the API must expose `command_results` and
    `validation_result` built from the Watcher's real execution pass
    (or gating).  This proves the Watcher is no longer returning a
    hard-coded success string — the response is assembled from the
    classifier + subprocess pass."""
    # 1. analyze an alert to create a pending record
    r = client.post(
        "/analyze",
        json={"alert_id": "E2E-APPROVE-001",
              "alert_text": "Disk usage 97% on /var/log volume, 'No space left on device' errors",
              "source": "pytest"},
    )
    assert r.status_code == 200

    # 2. approve it — Watcher should now run its classifier + subprocess
    r2 = client.post("/approve/E2E-APPROVE-001", params={"approved": "true"})
    assert r2.status_code == 200
    data = r2.json()
    assert data["approved"] is True
    assert data["execution_status"] in {"executed", "partially_executed"}
    # Plumbing surfaces the new fields
    assert "validation_result" in data
    assert "command_results" in data
    assert isinstance(data["command_results"], list)
    # validation_result must be built from real output — it includes either
    # an EXECUTED marker (safe command ran) or a GATED marker (mutation
    # held).  The old hard-coded "Fix applied successfully. All checks
    # passed." string must NOT appear.
    assert "All checks passed" not in data["validation_result"]
    # Every per-command result carries the schema the Watcher produces
    for cr in data["command_results"]:
        assert "classification" in cr
        assert cr["classification"] in {"safe", "mutation", "unknown"}
        assert "executed" in cr


def test_graph_invocation_retrieves_docs_from_rag() -> None:
    """Direct graph invocation should populate retrieved_docs with at least
    one chunk — the HTTP response does not surface this field, so we verify
    it here at the state level."""
    state = nexus_graph.invoke(
        _initial_state("E2E-STATE-001", "CPU usage 98% on api-gateway, OOM errors in logs")
    )

    retrieved = state.get("retrieved_docs", [])
    assert isinstance(retrieved, list), "retrieved_docs must be a list"
    assert len(retrieved) >= 1, "Maven must retrieve at least one runbook chunk"

    # Each chunk should have the contract fields produced by rag/retriever.py
    for doc in retrieved:
        assert "content" in doc and doc["content"].strip(), "chunk missing content"
        assert "source" in doc and doc["source"].endswith(".md"), "chunk missing source runbook"
        assert "score" in doc and 0.0 <= float(doc["score"]) <= 1.0, \
            f"similarity score out of [0,1]: {doc.get('score')}"

    # Confidence must be in-band and the iteration counter must advance
    assert 0.0 <= float(state["confidence_diagnose"]) <= 1.0
    assert state["iteration_count"] >= 1, "Maven did not increment iteration_count"
