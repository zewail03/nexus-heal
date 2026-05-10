"""
Smoke-test every dashboard page by exercising the API + RAG it depends on.

Run BOTH services first:
    python main.py
    python -m streamlit run ui/app.py

Then in a third terminal:
    python test_pages.py

Tests, page by page:
    1. Mission Control   -> /health + /alerts + Streamlit reachability
    2. Submit Alert      -> /analyze + /approve (full Sentinel-Watcher pipeline)
    3. Agent Graph       -> page is a static Graphviz render; we just check
                            Streamlit serves it
    4. RAG Debug         -> rag.retriever.retrieve_docs() returns top-k

Exits 0 if everything passes, non-zero otherwise.
"""
from __future__ import annotations

import sys
import time
from typing import Any

import httpx


API = "http://127.0.0.1:8000"
UI = "http://localhost:8501"

# ANSI colours for TTY output
GREEN = "\033[32m"
RED = "\033[31m"
YEL = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"

results: list[tuple[str, bool, str]] = []


def record(name: str, passed: bool, detail: str = "") -> None:
    results.append((name, passed, detail))
    tag = f"{GREEN}[PASS]{RESET}" if passed else f"{RED}[FAIL]{RESET}"
    print(f"  {tag} {name}" + (f"  {DIM}{detail}{RESET}" if detail else ""))


def header(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Page 1: Mission Control
# ---------------------------------------------------------------------------

def test_mission_control() -> None:
    header("Page 1 / Mission Control")

    # 1a. /health (sidebar online pill)
    try:
        r = httpx.get(f"{API}/health", timeout=4)
        ok = r.status_code == 200 and r.json().get("status") == "ok"
        record("/health endpoint reachable", ok, f"HTTP {r.status_code}")
    except Exception as e:
        record("/health endpoint reachable", False, f"{type(e).__name__}: {e}")
        return

    # 1b. /alerts (KPI tiles + card grid data source)
    try:
        r = httpx.get(f"{API}/alerts", timeout=10)
        ok = r.status_code == 200 and isinstance(r.json(), dict)
        n = len(r.json()) if ok else 0
        record("/alerts returns dict of alerts", ok, f"{n} alerts in store")
    except Exception as e:
        record("/alerts returns dict of alerts", False, f"{type(e).__name__}: {e}")
        return

    # 1c. KPI fields exist on each alert
    alerts = r.json()
    if alerts:
        sample = next(iter(alerts.values()))
        required_fields = {"alert_type", "severity", "confidence", "status"}
        missing = required_fields - set(sample.keys())
        record(
            "alert objects expose Mission Control fields",
            not missing,
            f"missing: {missing}" if missing else f"sample has all {len(required_fields)} fields",
        )
    else:
        record("alert objects expose Mission Control fields", True,
               "no alerts to inspect (skipped) — run demo/preload first if you want data")

    # 1d. Streamlit reachable (so the page can actually render)
    try:
        r = httpx.get(UI, timeout=5)
        ok = r.status_code == 200
        record("Streamlit dashboard reachable", ok, f"HTTP {r.status_code}")
    except Exception as e:
        record("Streamlit dashboard reachable", False, f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Page 2: Submit Alert (the showcase page)
# ---------------------------------------------------------------------------

def test_submit_alert() -> None:
    header("Page 2 / Submit Alert  (full Sentinel -> Watcher pipeline)")

    alert_id = f"PAGES-TEST-{int(time.time())}"
    alert_text = "CPU usage 99% on api-gateway-prod, OOM killer active"

    # 2a. /analyze runs the full LangGraph pipeline
    print(f"  {DIM}Submitting {alert_id} (this calls Groq, ~10s)...{RESET}")
    try:
        r = httpx.post(
            f"{API}/analyze",
            json={"alert_id": alert_id, "alert_text": alert_text, "source": "test_pages"},
            timeout=90,
        )
        ok = r.status_code == 200
        record("/analyze accepts alert and returns 200", ok, f"HTTP {r.status_code}")
        if not ok:
            return
        result = r.json()
    except Exception as e:
        record("/analyze accepts alert and returns 200", False, f"{type(e).__name__}: {e}")
        return

    # 2b. Sentinel populated alert_type + severity
    record(
        "Sentinel classified alert",
        bool(result.get("alert_type") and result.get("severity")),
        f"type={result.get('alert_type')} severity={result.get('severity')}",
    )

    # 2c. Maven returned diagnosis + retrieved docs
    diag = result.get("diagnosis") or ""
    record(
        "Maven produced diagnosis (>=20 chars)",
        len(diag) >= 20,
        f"{len(diag)} chars",
    )

    # 2d. Healer produced fix_plan + commands
    fix_plan = result.get("fix_plan") or []
    fix_cmds = result.get("fix_commands") or []
    record(
        "Healer produced fix plan + commands",
        len(fix_plan) >= 1 and len(fix_cmds) >= 1,
        f"{len(fix_plan)} steps, {len(fix_cmds)} commands",
    )

    # 2e. Confidence is a sane float in [0, 1]
    conf = result.get("confidence", 0.0)
    record(
        "Confidence gauge value in [0, 1]",
        isinstance(conf, (int, float)) and 0.0 <= conf <= 1.0,
        f"confidence = {conf}",
    )

    # 2f. /approve fires the Watcher
    try:
        r = httpx.post(
            f"{API}/approve/{alert_id}",
            params={"approved": "true"},
            timeout=30,
        )
        outcome = r.json() if r.status_code == 200 else {}
        cmd_results = outcome.get("command_results", [])
        executed = sum(1 for c in cmd_results if c.get("executed"))
        record(
            "/approve triggered Watcher",
            r.status_code == 200,
            f"status={outcome.get('execution_status')}  "
            f"({executed}/{len(cmd_results)} safe commands ran for real)",
        )
    except Exception as e:
        record("/approve triggered Watcher", False, f"{type(e).__name__}: {e}")
        return

    # 2g. Approved alert is reflected in /alerts (so Mission Control will show it)
    try:
        r = httpx.get(f"{API}/alerts", timeout=10)
        alerts_now = r.json()
        record(
            "approved alert visible in /alerts",
            alert_id in alerts_now and alerts_now[alert_id].get("status") in
            {"executed", "partially_executed"},
            f"status={alerts_now.get(alert_id, {}).get('status')}",
        )
    except Exception as e:
        record("approved alert visible in /alerts", False, f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Page 3: Agent Graph
# ---------------------------------------------------------------------------

def test_agent_graph() -> None:
    header("Page 3 / Agent Graph  (static Graphviz render)")

    # The Agent Graph page is a static Graphviz chart -- no API calls.
    # We just verify Streamlit is up so the user can navigate to it.
    try:
        r = httpx.get(UI, timeout=5)
        record(
            "Streamlit serves the dashboard (Agent Graph page reachable)",
            r.status_code == 200,
            "navigate to 'Agent Graph' in the sidebar to see the topology",
        )
    except Exception as e:
        record("Streamlit serves the dashboard", False, f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Page 4: RAG Debug
# ---------------------------------------------------------------------------

def test_rag_debug() -> None:
    header("Page 4 / RAG Debug  (ChromaDB retrieval)")

    try:
        from rag.retriever import retrieve_docs
        from rag.vectorstore import setup_vectorstore
    except Exception as e:
        record("RAG modules importable", False, f"{type(e).__name__}: {e}")
        return
    record("RAG modules importable", True, "rag.retriever, rag.vectorstore")

    # 4a. Vectorstore populated
    try:
        setup_vectorstore()  # idempotent — only ingests if empty
        record("ChromaDB vectorstore initialised", True, "")
    except Exception as e:
        record("ChromaDB vectorstore initialised", False, f"{type(e).__name__}: {e}")
        return

    # 4b. Retrieve returns top-k for a sane query
    try:
        docs = retrieve_docs(query="CPU spike on production", alert_type="", top_k=5)
        record(
            "retrieve_docs returns chunks",
            isinstance(docs, list) and len(docs) >= 1,
            f"{len(docs)} chunks returned",
        )
    except Exception as e:
        record("retrieve_docs returns chunks", False, f"{type(e).__name__}: {e}")
        return

    # 4c. Each chunk has the fields the page renders (source / score / content)
    if docs:
        d = docs[0]
        required = {"source", "score", "content"}
        missing = required - set(d.keys())
        record(
            "each chunk exposes RAG Debug fields",
            not missing,
            f"missing: {missing}" if missing else "source, score, content all present",
        )
        # 4d. Top score is a sane similarity value (0-1 for cosine)
        score = d.get("score", -1)
        record(
            "top-1 similarity score in [0, 1]",
            isinstance(score, (int, float)) and 0.0 <= score <= 1.0,
            f"top-1 score = {score:.4f}",
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print()
    print(f"NEXUS-HEAL dashboard page tests")
    print(f"  API: {API}")
    print(f"  UI : {UI}")

    test_mission_control()
    test_submit_alert()
    test_agent_graph()
    test_rag_debug()

    # Summary
    header("Summary")
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    failed = [(n, d) for n, ok, d in results if not ok]

    if failed:
        print(f"  {RED}{len(failed)} failed{RESET} / {total} total")
        for n, d in failed:
            print(f"    - {n}: {d}")
        print()
        print(f"  Hint: are both services running?")
        print(f"        Terminal 1: python main.py")
        print(f"        Terminal 2: python -m streamlit run ui/app.py")
        return 1

    print(f"  {GREEN}{passed}/{total} passed{RESET}")
    print()
    print(f"  Now click through the dashboard at {UI}:")
    print(f"    -> Mission Control : the new alert should appear at the top")
    print(f"    -> Submit Alert    : try a 'Quick preset' button; watch the pipeline animate")
    print(f"    -> Agent Graph     : Sentinel -> Maven -> Healer -> Watcher topology")
    print(f"    -> RAG Debug       : type 'kafka consumer lag' and inspect the chunks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
