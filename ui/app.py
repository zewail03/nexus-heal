"""
NEXUS-HEAL — Streamlit dashboard.

Four pages:
    1. Mission Control      - live system status + recent alert grid + KPIs
    2. Submit Alert         - hero input -> animated pipeline -> Watcher terminal
    3. Agent Graph          - architectural view of the StateGraph
    4. RAG Debug            - retrieval inspector with score bars

All visual styling lives in ui/styles.py; reusable components in
ui/components.py. This file owns layout and orchestration only.
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx
import streamlit as st

from ui import components as cx
from ui.styles import inject as inject_theme


# In single-container deployments (e.g. Render) the FastAPI process runs
# alongside Streamlit on the loopback interface. NEXUS_API_URL lets the
# deployer override this for split-service or remote-API setups.
FASTAPI_URL = os.getenv("NEXUS_API_URL", "http://127.0.0.1:8000")


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="NEXUS-HEAL",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_theme()


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def call_analyze(alert_id: str, alert_text: str) -> dict | None:
    try:
        resp = httpx.post(
            f"{FASTAPI_URL}/analyze",
            json={"alert_id": alert_id, "alert_text": alert_text, "source": "ui"},
            timeout=90,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def call_approve(alert_id: str, approved: bool) -> dict | None:
    try:
        resp = httpx.post(
            f"{FASTAPI_URL}/approve/{alert_id}",
            params={"approved": str(approved).lower()},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Approve error: {e}")
        return None


def fetch_alerts() -> dict[str, Any]:
    try:
        resp = httpx.get(f"{FASTAPI_URL}/alerts", timeout=10)
        return resp.json()
    except Exception:
        return {}


def check_health() -> bool:
    try:
        resp = httpx.get(f"{FASTAPI_URL}/health", timeout=4)
        return resp.json().get("status") == "ok"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        '<div style="font-size: 0.72rem; letter-spacing: 0.20em; '
        'color: var(--nx-text-dim); text-transform: uppercase; margin-bottom: 0.3rem;">'
        'NEXUS-HEAL</div>'
        '<div style="font-size: 1.05rem; font-weight: 700; line-height: 1.3; margin-bottom: 1rem;">'
        'Self-healing infrastructure agent</div>',
        unsafe_allow_html=True,
    )
    online = check_health()
    cx.system_pill(online)
    st.markdown("&nbsp;", unsafe_allow_html=True)

    page = st.radio(
        "Navigate",
        ["Mission Control", "Submit Alert", "Agent Graph", "RAG Debug"],
        label_visibility="collapsed",
    )

    st.markdown("&nbsp;", unsafe_allow_html=True)
    st.markdown(
        '<div class="nx-card" style="padding: 0.85rem 1rem;">'
        '<div class="nx-card-title" style="margin-bottom: 0.4rem;">Pipeline</div>'
        '<div style="font-size: 0.85rem; line-height: 1.7;">'
        '🧭 <strong>Sentinel</strong> — classify<br>'
        '📚 <strong>Maven</strong> — RAG diagnose<br>'
        '🔧 <strong>Healer</strong> — fix plan<br>'
        '🛡️ <strong>Watcher</strong> — execute'
        '</div></div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Page: Mission Control
# ---------------------------------------------------------------------------

def page_mission_control() -> None:
    cx.hero(
        "Mission Control",
        "Network Expert Unified System for Healing, Error-Analysis & Logging — "
        "live incident telemetry across the LangGraph pipeline."
    )

    if not online:
        st.warning(
            "FastAPI is not reachable at "
            f"`{FASTAPI_URL}` — start it with `python main.py` and refresh."
        )
        return

    alerts = fetch_alerts()
    total = len(alerts)
    by_status: dict[str, int] = {}
    by_sev: dict[str, int] = {}
    confidences: list[float] = []
    for a in alerts.values():
        by_status[a.get("status", "pending")] = by_status.get(a.get("status", "pending"), 0) + 1
        by_sev[(a.get("severity") or "n/a").upper()] = by_sev.get((a.get("severity") or "n/a").upper(), 0) + 1
        if a.get("confidence") is not None:
            confidences.append(float(a["confidence"]))

    avg_conf = (sum(confidences) / len(confidences)) if confidences else 0.0
    crit = by_sev.get("CRITICAL", 0)
    high = by_sev.get("HIGH", 0)
    executed = by_status.get("executed", 0) + by_status.get("partially_executed", 0)

    c1, c2, c3, c4 = st.columns(4)
    with c1: cx.kpi_card("Alerts processed", str(total), "since server boot")
    with c2: cx.kpi_card("Critical / High",  f"{crit} / {high}", "by severity")
    with c3: cx.kpi_card("Avg. diagnosis confidence", f"{int(avg_conf*100)}%",
                        "blended LLM × RAG × specificity")
    with c4: cx.kpi_card("Fixes executed", str(executed), "approved + run")

    st.markdown("&nbsp;", unsafe_allow_html=True)

    if not alerts:
        st.markdown(
            '<div class="nx-card" style="text-align:center; padding: 2rem;">'
            '<div style="font-size: 1.1rem; margin-bottom: 0.6rem;">No incidents yet</div>'
            '<div class="nx-card-sub">Submit one from the <em>Submit Alert</em> tab, '
            'or run <code>python -m demo.preload</code> to seed the dashboard.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    # Two-column grid of alert cards, newest first (best-effort: reverse insertion order)
    items = list(alerts.items())[::-1]
    cols = st.columns(2)
    for i, (alert_id, data) in enumerate(items):
        with cols[i % 2]:
            cx.alert_card(alert_id, data)


# ---------------------------------------------------------------------------
# Page: Submit Alert (the showcase page)
# ---------------------------------------------------------------------------

def page_submit_alert() -> None:
    cx.hero(
        "Submit Alert",
        "Watch all four agents run in real time — Sentinel classifies, "
        "Maven retrieves, Healer plans, Watcher executes the safe verifications."
    )

    if not online:
        st.warning(f"FastAPI is not reachable at `{FASTAPI_URL}`. Start it with `python main.py`.")
        return

    # -- Input ---------------------------------------------------------------
    demo_alerts = {
        "🔥 CPU spike":     "CPU usage 98.7% on api-gateway-prod, OOM killer active, connection pool exhausted",
        "💾 DB connection": "Database connection pool exhausted on primary PostgreSQL, 503 errors on /api/users",
        "📀 Disk full":     "Disk usage 97% on /var/log volume, application failing to write logs",
        "🔐 SSL expired":   "SSL certificate expired on api.example.com, HTTPS handshake failures across all clients",
        "📦 Pod crash":     "payment-service pod in CrashLoopBackOff, exit code 137, restart count at 12",
    }

    # Initialise the textarea's own widget key once. The widget owns its
    # state via `key="alert_text_input"` from here on.
    if "alert_text_input" not in st.session_state:
        st.session_state.alert_text_input = ""

    # Callbacks run BEFORE the next render so they can legally modify
    # widget state — unlike click handlers in the main render flow.
    def _apply_preset(preset_text: str) -> None:
        st.session_state.alert_text_input = preset_text
        st.session_state.auto_run = True

    cols = st.columns([3, 2])
    with cols[0]:
        st.markdown(
            '<div class="nx-card-title">Alert text</div>',
            unsafe_allow_html=True,
        )
        alert_text = st.text_area(
            "alert text",
            placeholder="e.g. CPU usage 98% on api-gateway-prod, OOM killer active",
            height=130,
            label_visibility="collapsed",
            key="alert_text_input",
        )

    with cols[1]:
        st.markdown(
            '<div class="nx-card-title">Quick presets</div>',
            unsafe_allow_html=True,
        )
        for label, text in demo_alerts.items():
            st.button(
                label,
                key=f"preset_{label}",
                use_container_width=True,
                on_click=_apply_preset,
                args=(text,),
            )

    run = st.button("▶  Analyze alert", type="primary", disabled=not alert_text)

    # If a preset was just clicked, auto-fire the analysis on this rerun.
    auto_run = st.session_state.pop("auto_run", False)

    # -- Execution -----------------------------------------------------------
    pipeline_slot = st.empty()
    pipeline_slot.markdown("", unsafe_allow_html=True)

    if (run or auto_run) and alert_text:
        # Animate pipeline stages — each step takes a tiny moment of UI lag,
        # then the real /analyze call replaces it with the final state.
        for active_idx, key in enumerate(["sentinel", "maven", "healer", "watcher"]):
            done = ["sentinel", "maven", "healer", "watcher"][:active_idx]
            with pipeline_slot.container():
                cx.render_pipeline(active=key, completed=done)
            time.sleep(0.45)

        alert_id = f"UI-{int(time.time())}"
        result = call_analyze(alert_id, alert_text)

        if not result:
            with pipeline_slot.container():
                cx.render_pipeline(active=None, completed=["sentinel", "maven", "healer"], error="watcher")
            return

        with pipeline_slot.container():
            cx.render_pipeline(active=None, completed=["sentinel", "maven", "healer", "watcher"])

        st.session_state.last_result = result
        st.session_state.last_alert_id = alert_id

    # -- Result panels -------------------------------------------------------
    result = st.session_state.get("last_result")
    if not result:
        return

    st.markdown("&nbsp;", unsafe_allow_html=True)

    # Top row: severity / type / confidence gauge / fetch retrieved docs hint
    a, b, c = st.columns([1.1, 1.1, 1.4])
    with a:
        st.markdown(
            f'<div class="nx-card">'
            f'<div class="nx-card-title">Classification</div>'
            f'<div style="font-size:1.45rem;font-weight:700;margin:0.2rem 0;">'
            f'{result.get("alert_type","unknown")}</div>'
            f'<div>{cx.severity_badge(result.get("severity",""))}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with b:
        cx.kpi_card(
            "Root cause",
            (result.get("root_cause") or "")[:48] + ("…" if len(result.get("root_cause") or "") > 48 else ""),
            (result.get("diagnosis") or "")[:120] + ("…" if len(result.get("diagnosis") or "") > 120 else ""),
        )
    with c:
        cx.confidence_gauge(result.get("confidence", 0.0), title="Diagnosis confidence")

    # Fix plan + commands
    p, q = st.columns(2)
    with p:
        st.markdown(
            '<div class="nx-card-title">Fix plan</div>',
            unsafe_allow_html=True,
        )
        plan = result.get("fix_plan", []) or []
        if plan:
            html_lines = "".join(
                f'<li style="margin: 0.35rem 0;"><span style="color: var(--nx-cyan); '
                f'font-weight: 700; margin-right: 0.4rem;">{i+1}.</span>'
                f'{step}</li>'
                for i, step in enumerate(plan)
            )
            st.markdown(
                f'<div class="nx-card"><ol style="padding-left: 1.1rem; margin: 0;">{html_lines}</ol></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="nx-card-sub">no plan returned</div>', unsafe_allow_html=True)
    with q:
        st.markdown(
            '<div class="nx-card-title">Fix commands</div>',
            unsafe_allow_html=True,
        )
        cmds = result.get("fix_commands", []) or []
        if cmds:
            for cmd in cmds:
                st.code(cmd, language="bash")
        else:
            st.markdown('<div class="nx-card-sub">no commands returned</div>', unsafe_allow_html=True)

    # Approval row
    st.markdown("&nbsp;", unsafe_allow_html=True)
    st.markdown(
        '<div class="nx-card-title">Operator decision</div>',
        unsafe_allow_html=True,
    )
    ac, rc = st.columns(2)
    with ac:
        if st.button("✅  Approve & execute (safe commands run for real)",
                     type="primary", use_container_width=True, key="approve_btn"):
            outcome = call_approve(st.session_state.last_alert_id, True)
            if outcome:
                st.session_state.last_outcome = outcome
                st.rerun()
    with rc:
        if st.button("⚠️  Reject & escalate", use_container_width=True, key="reject_btn"):
            outcome = call_approve(st.session_state.last_alert_id, False)
            if outcome:
                st.session_state.last_outcome = outcome
                st.rerun()

    # Watcher output
    outcome = st.session_state.get("last_outcome")
    if outcome:
        st.markdown("&nbsp;", unsafe_allow_html=True)
        sl, sr = st.columns([1.4, 1])
        with sl:
            st.markdown(
                '<div class="nx-card-title">Watcher execution log</div>',
                unsafe_allow_html=True,
            )
            cx.watcher_terminal(outcome.get("command_results", []))
        with sr:
            st.markdown(
                '<div class="nx-card-title">Outcome</div>',
                unsafe_allow_html=True,
            )
            executed_total = sum(1 for r in outcome.get("command_results", []) if r.get("executed"))
            gated_total = sum(1 for r in outcome.get("command_results", []) if not r.get("executed"))
            st.markdown(
                f'<div class="nx-card">'
                f'<div style="margin-bottom: 0.5rem;">{cx.status_badge(outcome.get("execution_status", ""))}</div>'
                f'<div class="nx-card-sub">Commands executed for real (read-only allowlist):</div>'
                f'<div class="nx-card-value" style="color: var(--nx-lime);">{executed_total}</div>'
                f'<div class="nx-card-sub" style="margin-top:0.6rem;">Gated for human review:</div>'
                f'<div class="nx-card-value" style="color: var(--nx-yellow);">{gated_total}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# Page: Agent Graph
# ---------------------------------------------------------------------------

def page_agent_graph() -> None:
    cx.hero(
        "Agent Graph",
        "LangGraph StateGraph topology — Sentinel and Maven loop on low confidence; "
        "Watcher gates mutation commands behind operator approval."
    )
    cx.render_pipeline()
    st.graphviz_chart("""
    digraph G {
        rankdir=LR
        bgcolor="transparent"
        node [shape=box style="rounded,filled" fontname="Inter" fontsize=12 color="#1e2740" fontcolor="#e6e8f0"]
        edge [fontname="Inter" fontsize=10 color="#8b91a9" fontcolor="#8b91a9"]

        sentinel [label="Sentinel"  fillcolor="#0e1a3c"]
        maven    [label="Maven"     fillcolor="#1a0e3c"]
        healer   [label="Healer"    fillcolor="#3c1f0e"]
        watcher  [label="Watcher"   fillcolor="#0e3c2a"]
        executed [label="Executed"  shape=ellipse fillcolor="#0a3320" fontcolor="#b2ff59"]
        gated    [label="Gated"     shape=ellipse fillcolor="#332a0a" fontcolor="#ffbe0b"]
        rejected [label="Rejected"  shape=ellipse fillcolor="#3c0a1e" fontcolor="#ff006e"]

        sentinel -> maven    [label="classify"]
        maven    -> maven    [label="confidence < 0.5\\n(retry, max 2)" style=dashed color="#fb5607" fontcolor="#fb5607"]
        maven    -> healer   [label="confidence ≥ 0.5"]
        healer   -> watcher  [label="fix plan"]
        watcher  -> executed [label="approved + safe"]
        watcher  -> gated    [label="approved + mutation"]
        watcher  -> rejected [label="not approved"]
    }
    """, use_container_width=True)

    st.markdown("&nbsp;", unsafe_allow_html=True)

    cards = [
        ("Sentinel",  "Alert classifier",
         "Maps raw alert text → one of 10 known types + severity + category. Calibrated 0-1 confidence."),
        ("Maven",     "RAG diagnoser",
         "Queries ChromaDB for top-3 runbook chunks (cosine, chunk=500/overlap=50), feeds to Llama 3.3 70B "
         "for root-cause + diagnosis. Confidence blended from LLM × RAG × alert specificity."),
        ("Healer",    "Fix plan generator",
         "Produces 3-5 step fix plan + concrete commands + rollback. No execution at this stage — that's the Watcher."),
        ("Watcher",   "Executor + escalation",
         "Classifies each fix_command into safe/mutation/unknown. Safe commands run via subprocess. "
         "Mutations gated for human review. validation_result is built from real captured stdout."),
    ]
    cols = st.columns(2)
    for i, (name, role, body) in enumerate(cards):
        with cols[i % 2]:
            st.markdown(
                f'<div class="nx-card" style="margin-bottom: 0.9rem;">'
                f'<div class="nx-card-title">{role}</div>'
                f'<div style="font-weight: 700; font-size: 1.15rem; margin-bottom: 0.4rem;">{name}</div>'
                f'<div class="nx-card-sub">{body}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# Page: RAG Debug
# ---------------------------------------------------------------------------

def page_rag_debug() -> None:
    cx.hero(
        "RAG Debug",
        "Query the production ChromaDB and inspect chunk-level similarity scores. "
        "Same retrieval path the Maven agent uses."
    )
    query = st.text_input("Search query",
                          placeholder="e.g. CPU spike on production server",
                          label_visibility="collapsed")
    top_k = st.slider("top_k", 1, 10, 5)
    if st.button("🔍  Search knowledge base", type="primary", disabled=not query):
        try:
            from rag.retriever import retrieve_docs
            docs = retrieve_docs(query=query, alert_type="", top_k=top_k)
        except Exception as e:
            st.error(f"RAG error: {e}")
            return

        if not docs:
            st.warning("No documents found. Run `python main.py` once to ingest the knowledge base.")
            return

        st.markdown("&nbsp;", unsafe_allow_html=True)
        st.markdown('<div class="nx-card-title">Similarity scores</div>', unsafe_allow_html=True)
        cx.retrieval_bars(docs)

        st.markdown("&nbsp;", unsafe_allow_html=True)
        st.markdown('<div class="nx-card-title">Retrieved chunks</div>', unsafe_allow_html=True)
        for i, doc in enumerate(docs, start=1):
            with st.expander(
                f"#{i}  {doc.get('source','?')}  —  score {doc.get('score',0.0):.3f}",
                expanded=(i == 1),
            ):
                st.markdown(f"**Doc id:** `{doc.get('doc_id','?')}`")
                st.markdown(f"**Alert type:** `{doc.get('alert_type','?')}`")
                st.markdown(f"**Score:** `{doc.get('score', 0.0):.4f}`")
                st.text(doc.get("content", ""))


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

if page == "Mission Control":
    page_mission_control()
elif page == "Submit Alert":
    page_submit_alert()
elif page == "Agent Graph":
    page_agent_graph()
elif page == "RAG Debug":
    page_rag_debug()
