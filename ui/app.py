import streamlit as st
import httpx
import time
import json

# ── Page config ──
st.set_page_config(
    page_title="NEXUS-HEAL Dashboard",
    page_icon="\U0001f6e1\ufe0f",
    layout="wide",
)

FASTAPI_URL = "http://127.0.0.1:8000"

# ── Sidebar ──
st.sidebar.title("NEXUS-HEAL")
st.sidebar.markdown("Network Expert Unified System for\nHealing, Error-Analysis & Logging")
st.sidebar.divider()
page = st.sidebar.radio("Navigate", ["Dashboard", "Submit Alert", "Agent Graph", "RAG Debug"])

# ── Helper: call API ──


def call_analyze(alert_id: str, alert_text: str) -> dict | None:
    try:
        resp = httpx.post(
            f"{FASTAPI_URL}/analyze",
            json={"alert_id": alert_id, "alert_text": alert_text, "source": "manual"},
            timeout=60,
        )
        return resp.json()
    except Exception as e:
        st.error(f"API Error: {e}")
        return None


def fetch_alerts() -> dict:
    try:
        resp = httpx.get(f"{FASTAPI_URL}/alerts", timeout=10)
        return resp.json()
    except Exception:
        return {}


def check_health() -> bool:
    try:
        resp = httpx.get(f"{FASTAPI_URL}/health", timeout=5)
        return resp.json().get("status") == "ok"
    except Exception:
        return False


# ── Page: Dashboard ──

if page == "Dashboard":
    st.title("NEXUS-HEAL Incident Dashboard")

    # Health check
    healthy = check_health()
    if healthy:
        st.success("System Online  |  FastAPI server is running")
    else:
        st.warning("System Offline  |  Start the server with `python main.py`")

    st.divider()

    # Incident history
    st.subheader("Incident History")
    alerts = fetch_alerts()

    if not alerts:
        st.info("No incidents processed yet. Submit an alert or use the Telegram bot.")
    else:
        for alert_id, data in alerts.items():
            severity = data.get("severity", "N/A")
            sev_colors = {"CRITICAL": "red", "HIGH": "orange", "MEDIUM": "yellow", "LOW": "green"}
            color = sev_colors.get(severity, "gray")

            with st.expander(f":{color}[{severity}]  {alert_id} — {data.get('alert_type', 'N/A')}"):
                col1, col2, col3 = st.columns(3)
                col1.metric("Confidence", f"{int(data.get('confidence', 0) * 100)}%")
                col2.metric("Status", data.get("status", "pending"))
                col3.metric("Type", data.get("alert_type", "N/A"))

                st.markdown(f"**Root Cause:** {data.get('root_cause', 'N/A')}")
                st.markdown(f"**Diagnosis:** {data.get('diagnosis', 'N/A')}")

                if data.get("fix_plan"):
                    st.markdown("**Fix Plan:**")
                    for i, step in enumerate(data["fix_plan"]):
                        st.markdown(f"{i+1}. {step}")


# ── Page: Submit Alert ──

elif page == "Submit Alert":
    st.title("Submit Alert")
    st.markdown("Enter an alert description to run the full NEXUS-HEAL pipeline.")

    alert_text = st.text_area(
        "Alert Description",
        placeholder="e.g., CPU usage 98% on api-gateway-prod, OOM errors in logs",
        height=100,
    )

    demo_alerts = {
        "CPU Spike": "CPU usage 98.7% on api-gateway-prod, OOM killer active, connection pool exhausted",
        "DB Connection": "Database connection pool exhausted on primary PostgreSQL, 503 errors on /api/users",
        "Disk Full": "Disk usage 97% on /var/log volume, application failing to write logs",
        "SSL Expired": "SSL certificate expired on prod domain api.example.com, HTTPS handshake failures",
        "Memory Leak": "Memory usage steadily climbing on payment-service pod, at 95% of 2Gi limit, OOMKilled twice today",
    }

    st.markdown("**Quick Demo Alerts:**")
    demo_cols = st.columns(len(demo_alerts))
    for col, (name, text) in zip(demo_cols, demo_alerts.items()):
        if col.button(name, use_container_width=True):
            alert_text = text

    if st.button("Analyze Alert", type="primary", disabled=not alert_text):
        alert_id = f"UI-{int(time.time())}"

        # Show agent pipeline progress
        agent_steps = ["Sentinel", "Maven", "Healer", "Watcher"]
        progress_cols = st.columns(4)

        # Step through agents visually
        for step_idx, agent_name in enumerate(agent_steps):
            for i, col in enumerate(progress_cols):
                with col:
                    if i < step_idx:
                        st.success(f"Done: {agent_steps[i]}")
                    elif i == step_idx:
                        st.info(f"Running: {agent_name}...")
                    else:
                        st.empty()

        with st.spinner("Running full pipeline..."):
            result = call_analyze(alert_id, alert_text)

        if result:
            # Mark all agents as done
            for i, col in enumerate(progress_cols):
                with col:
                    st.success(f"Done: {agent_steps[i]}")

            st.divider()
            st.subheader("Diagnosis Result")

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Alert Type", result.get("alert_type", "N/A"))
            col2.metric("Severity", result.get("severity", "N/A"))
            col3.metric("Confidence", f"{int(float(result.get('confidence', 0)) * 100)}%")
            col4.metric("Status", result.get("status", "pending"))

            st.markdown(f"**Root Cause:** {result.get('root_cause', 'N/A')}")
            st.markdown(f"**Diagnosis:** {result.get('diagnosis', 'N/A')}")

            st.subheader("Fix Plan")
            for i, step in enumerate(result.get("fix_plan", [])):
                st.markdown(f"{i+1}. {step}")

            st.subheader("Fix Commands")
            for cmd in result.get("fix_commands", []):
                st.code(cmd, language="bash")

            st.markdown(f"**Rollback Plan:** {result.get('rollback_plan', 'N/A')}")
            st.markdown(f"**Estimated Time:** {result.get('estimated_time', 'N/A')}")

            # Approve / Reject
            st.divider()
            approve_col, reject_col = st.columns(2)
            if approve_col.button("Approve & Execute", type="primary", use_container_width=True):
                try:
                    httpx.post(f"{FASTAPI_URL}/approve/{alert_id}", params={"approved": "true"}, timeout=10)
                    st.success("Fix approved and executed! Watcher is monitoring.")
                except Exception as e:
                    st.error(f"Error: {e}")
            if reject_col.button("Reject & Escalate", use_container_width=True):
                try:
                    httpx.post(f"{FASTAPI_URL}/approve/{alert_id}", params={"approved": "false"}, timeout=10)
                    st.warning("Fix rejected. Escalated to senior engineer.")
                except Exception as e:
                    st.error(f"Error: {e}")


# ── Page: Agent Graph ──

elif page == "Agent Graph":
    st.title("LangGraph Agent Pipeline")
    st.markdown("Visual representation of the NEXUS-HEAL multi-agent pipeline.")

    # Draw the pipeline as a Graphviz diagram
    st.graphviz_chart("""
    digraph G {
        rankdir=LR
        bgcolor="transparent"
        node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=12 color="#444444"]
        edge [fontname="Helvetica" fontsize=10]

        sentinel [label="Sentinel Agent" fillcolor="#4A90D9" fontcolor="white"]
        maven    [label="Maven Agent"    fillcolor="#7B68EE" fontcolor="white"]
        healer   [label="Healer Agent"   fillcolor="#E67E22" fontcolor="white"]
        watcher  [label="Watcher Agent"  fillcolor="#2ECC71" fontcolor="white"]
        executed [label="Executed"  shape=ellipse fillcolor="#27AE60" fontcolor="white"]
        escalated[label="Escalated" shape=ellipse fillcolor="#E74C3C" fontcolor="white"]

        sentinel -> maven    [label="classify"]
        maven    -> maven    [label="confidence < 0.5\\n(retry)" style=dashed]
        maven    -> healer   [label="confidence >= 0.5"]
        healer   -> watcher  [label="fix plan"]
        watcher  -> executed [label="approved"]
        watcher  -> escalated[label="rejected"]
    }
    """, use_container_width=True)

    st.divider()

    st.subheader("Agent Details")

    agents_info = {
        "Sentinel": {
            "role": "Alert Classifier",
            "input": "Raw alert text",
            "output": "alert_type, severity, category, confidence",
            "file": "agents/sentinel.py",
        },
        "Maven": {
            "role": "RAG Diagnoser",
            "input": "Classified alert + knowledge base",
            "output": "diagnosis, root_cause, confidence, similar_incidents",
            "file": "agents/maven.py",
        },
        "Healer": {
            "role": "Fix Plan Generator",
            "input": "Diagnosis + retrieved runbooks",
            "output": "fix_plan, fix_commands, rollback_plan",
            "file": "agents/healer.py",
        },
        "Watcher": {
            "role": "Validation Monitor",
            "input": "Human approval + fix plan",
            "output": "execution_status, validation_result, final_message",
            "file": "agents/watcher.py",
        },
    }

    for name, info in agents_info.items():
        with st.expander(f"{name} Agent"):
            st.markdown(f"**Role:** {info['role']}")
            st.markdown(f"**Input:** {info['input']}")
            st.markdown(f"**Output:** {info['output']}")
            st.markdown(f"**Source:** `{info['file']}`")


# ── Page: RAG Debug ──

elif page == "RAG Debug":
    st.title("RAG Debug Panel")
    st.markdown("Test the RAG retrieval system directly.")

    query = st.text_input("Search query", placeholder="e.g., CPU spike on production server")

    if st.button("Search Knowledge Base") and query:
        try:
            from rag.retriever import retrieve_docs

            docs = retrieve_docs(query=query, alert_type="", top_k=5)

            if not docs:
                st.warning("No documents found. Make sure the knowledge base has been ingested.")
            else:
                st.success(f"Found {len(docs)} relevant chunks")
                for doc in docs:
                    with st.expander(f"Score: {doc['score']:.4f} | Source: {doc['source']}"):
                        st.markdown(f"**Doc ID:** `{doc['doc_id']}`")
                        st.markdown(f"**Alert Type:** `{doc['alert_type']}`")
                        st.markdown(f"**Similarity Score:** `{doc['score']:.4f}`")
                        st.divider()
                        st.text(doc["content"])
        except Exception as e:
            st.error(f"RAG Error: {e}")
            st.info("Make sure to run `python main.py` first to ingest the knowledge base.")
