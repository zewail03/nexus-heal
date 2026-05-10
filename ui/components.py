"""
NEXUS-HEAL — reusable Streamlit UI components.

Every component renders self-contained HTML inside a Streamlit
container, using the CSS in `ui.styles`.  Plotly is used for the
radial confidence gauge; everything else is hand-rolled HTML+CSS.
"""
from __future__ import annotations

import html
import json
from typing import Iterable, Sequence

import plotly.graph_objects as go
import streamlit as st


# ---------------------------------------------------------------------------
# Severity helpers
# ---------------------------------------------------------------------------

_SEVERITY_CSS = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
}


def severity_badge(severity: str) -> str:
    """Return the inline HTML for a severity pill."""
    cls = _SEVERITY_CSS.get((severity or "").upper(), "muted")
    label = (severity or "n/a").upper()
    return f'<span class="nx-badge {cls}">{html.escape(label)}</span>'


def status_badge(status: str) -> str:
    cls_map = {
        "executed":            "low",
        "partially_executed":  "medium",
        "rejected":            "high",
        "pending":             "info",
    }
    cls = cls_map.get(status, "muted")
    return f'<span class="nx-badge {cls}">{html.escape(status or "unknown")}</span>'


# ---------------------------------------------------------------------------
# KPI card
# ---------------------------------------------------------------------------

def kpi_card(title: str, value: str, sub: str | None = None) -> None:
    sub_html = f'<div class="nx-card-sub">{html.escape(sub)}</div>' if sub else ""
    st.markdown(
        f"""<div class="nx-card">
            <div class="nx-card-title">{html.escape(title)}</div>
            <div class="nx-card-value">{html.escape(value)}</div>
            {sub_html}
        </div>""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Animated pipeline — Sentinel -> Maven -> Healer -> Watcher
# ---------------------------------------------------------------------------

PIPELINE_STAGES: tuple[tuple[str, str, str], ...] = (
    ("sentinel", "Sentinel", "Classifier"),
    ("maven",    "Maven",    "RAG Diagnose"),
    ("healer",   "Healer",   "Fix Plan"),
    ("watcher",  "Watcher",  "Execute"),
)

_STAGE_ICONS = {
    "sentinel": "\U0001f9ed",  # compass
    "maven":    "\U0001f4da",  # books
    "healer":   "\U0001f527",  # wrench
    "watcher":  "\U0001f6e1",  # shield
}


def render_pipeline(active: str | None = None,
                    completed: Sequence[str] = (),
                    error: str | None = None) -> None:
    """Render the 4-stage pipeline with a glow on the active stage,
    checks on completed stages, and a red border on an errored stage."""
    completed_set = set(completed)
    parts: list[str] = ['<div class="nx-pipeline">']
    for i, (key, name, label) in enumerate(PIPELINE_STAGES):
        if key == error:
            cls, suffix = "error", '<span class="check">!</span>'
        elif key in completed_set:
            cls, suffix = "done", '<span class="check">✓</span>'
        elif key == active:
            cls, suffix = "running", '<span class="spin">○</span>'
        else:
            cls, suffix = "idle", ""
        icon = _STAGE_ICONS.get(key, "")
        parts.append(
            f'<div class="nx-stage {cls}">'
            f'<div class="stage-label">{label}</div>'
            f'<div class="stage-name"><span><span class="stage-icon">{icon}</span>{name}</span>{suffix}</div>'
            f'</div>'
        )
        if i < len(PIPELINE_STAGES) - 1:
            parts.append('<div class="nx-arrow">→</div>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Confidence radial gauge (Plotly)
# ---------------------------------------------------------------------------

def confidence_gauge(value: float, *, title: str = "Confidence", height: int = 220) -> None:
    """Render a circular indicator gauge in [0, 1]."""
    pct = max(0.0, min(1.0, float(value or 0.0)))
    bar_color = "#00d4ff" if pct >= 0.7 else "#ffbe0b" if pct >= 0.5 else "#fb5607"
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=pct * 100,
        number={"suffix": "%", "font": {"color": "#e6e8f0", "size": 32}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": "#8b91a9",
                     "tickfont": {"color": "#8b91a9", "size": 10}},
            "bar": {"color": bar_color, "thickness": 0.30},
            "bgcolor": "rgba(13,18,36,0)",
            "borderwidth": 0,
            "steps": [
                {"range": [0, 50],  "color": "rgba(251, 86, 7, 0.10)"},
                {"range": [50, 70], "color": "rgba(255, 190, 11, 0.10)"},
                {"range": [70, 100],"color": "rgba(0, 212, 255, 0.12)"},
            ],
            "threshold": {"line": {"color": "#fff", "width": 2}, "thickness": 0.85, "value": pct * 100},
        },
        title={"text": f"<span style='color:#8b91a9;font-size:0.78rem;letter-spacing:0.18em'>{title.upper()}</span>"},
        domain={"x": [0, 1], "y": [0, 1]},
    ))
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, sans-serif"},
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ---------------------------------------------------------------------------
# RAG retrieval bars
# ---------------------------------------------------------------------------

def retrieval_bars(docs: Sequence[dict]) -> None:
    """Render each retrieved chunk as a horizontal score bar."""
    if not docs:
        st.markdown('<div class="nx-card-sub">no chunks retrieved</div>', unsafe_allow_html=True)
        return
    rows: list[str] = []
    for d in docs:
        score = float(d.get("score", 0.0))
        pct = max(0.0, min(1.0, score)) * 100
        source = d.get("source", "unknown.md").replace("runbook_", "").replace(".md", "")
        rows.append(
            f'<div class="nx-bar-row">'
            f'  <div class="nx-bar-label">{html.escape(source)}</div>'
            f'  <div class="nx-bar-track"><div class="nx-bar-fill" style="width: {pct:.1f}%"></div></div>'
            f'  <div class="nx-bar-value">{score:.3f}</div>'
            f'</div>'
        )
    st.markdown("".join(rows), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Watcher terminal-style output
# ---------------------------------------------------------------------------

def watcher_terminal(command_results: Iterable[dict]) -> None:
    """Render command_results from the Watcher as a coloured terminal log."""
    results = list(command_results or [])
    if not results:
        st.markdown(
            '<div class="nx-terminal"><span class="nx-terminal-line unknown">'
            '$ no commands captured yet — approve a fix to populate this view'
            '</span></div>',
            unsafe_allow_html=True,
        )
        return
    lines: list[str] = ['<div class="nx-terminal">']
    for r in results:
        cmd = html.escape(r.get("command", ""))
        cls_attr = r.get("classification", "unknown")
        if r.get("executed"):
            tag = "exec" if r.get("exit_code") == 0 else "fail"
            tag_text = "OK" if tag == "exec" else f"FAIL exit={r.get('exit_code')}"
            lines.append(
                f'<div class="nx-terminal-line {tag}">'
                f'<span style="opacity:0.55">[{tag_text}]</span> '
                f'<span class="nx-terminal-cmd">$ {cmd}</span>'
                f'</div>'
            )
            stdout = (r.get("stdout") or "").strip()
            if stdout:
                preview = stdout.splitlines()[:3]
                for line in preview:
                    lines.append(
                        f'<div class="nx-terminal-stdout">{html.escape(line)[:180]}</div>'
                    )
        else:
            tag = "gated" if cls_attr in ("mutation", "unknown") else "fail"
            label = f"GATED {cls_attr}" if tag == "gated" else "EXEC-FAILED"
            reason = r.get("error") or ""
            reason_html = (
                f' <span style="opacity:0.7">— {html.escape(reason)}</span>' if reason else ""
            )
            lines.append(
                f'<div class="nx-terminal-line {tag}">'
                f'<span style="opacity:0.55">[{label}]</span> '
                f'<span class="nx-terminal-cmd">$ {cmd}</span>{reason_html}'
                f'</div>'
            )
    lines.append("</div>")
    st.markdown("".join(lines), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Compact alert card for the dashboard grid
# ---------------------------------------------------------------------------

def alert_card(alert_id: str, data: dict) -> None:
    severity = (data.get("severity") or "n/a").upper()
    alert_type = data.get("alert_type") or "unknown"
    confidence = float(data.get("confidence") or 0.0)
    status = data.get("status") or "pending"
    root_cause = data.get("root_cause") or "(no diagnosis)"
    body = html.escape(root_cause[:160] + ("…" if len(root_cause) > 160 else ""))
    # NOTE: leading whitespace on each line would make Streamlit's markdown
    # parser treat the HTML as a code block. Keep this as one logical line
    # (or call textwrap.dedent) so the card renders, not the raw markup.
    markup = (
        f'<div class="nx-card" style="margin-bottom: 0.9rem">'
        f'<div style="display:flex; justify-content: space-between; align-items: center; gap: 0.6rem; margin-bottom: 0.3rem;">'
        f'<div style="font-size:0.75rem; color: var(--nx-text-dim); letter-spacing: 0.14em; text-transform: uppercase;">'
        f'{html.escape(alert_id)}'
        f'</div>'
        f'<div style="display:flex; gap: 0.4rem;">'
        f'{severity_badge(severity)}'
        f'{status_badge(status)}'
        f'</div>'
        f'</div>'
        f'<div style="font-weight: 700; font-size: 1.05rem; margin-bottom: 0.2rem;">'
        f'{html.escape(alert_type)} '
        f'<span style="color: var(--nx-text-dim); font-weight: 400; font-size: 0.85rem;">'
        f'— confidence {int(confidence*100)}%</span>'
        f'</div>'
        f'<div style="color: var(--nx-text-dim); font-size: 0.88rem; line-height: 1.45;">{body}</div>'
        f'</div>'
    )
    st.markdown(markup, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Hero header
# ---------------------------------------------------------------------------

def hero(title: str, tagline: str | None = None) -> None:
    tagline_html = (
        f'<div style="color: var(--nx-text-dim); font-size: 1.0rem; max-width: 720px; '
        f'line-height: 1.55; margin-top: 0.25rem;">{html.escape(tagline)}</div>'
        if tagline else ""
    )
    st.markdown(
        f"""<div style="margin: 0.4rem 0 1.4rem 0;">
            <h1 style="margin-bottom: 0.1rem;">{html.escape(title)}</h1>
            {tagline_html}
        </div>""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# System-status pill (sidebar)
# ---------------------------------------------------------------------------

def system_pill(online: bool) -> None:
    if online:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:0.5rem;'
            'padding:0.5rem 0.7rem;background:rgba(178,255,89,0.07);'
            'border:1px solid rgba(178,255,89,0.30);border-radius:10px;'
            'font-size:0.85rem;">'
            '<span style="width:8px;height:8px;background:#b2ff59;'
            'border-radius:50%;box-shadow:0 0 8px #b2ff59;animation:stage-pulse 1.6s infinite"></span>'
            'API <strong>online</strong></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:0.5rem;'
            'padding:0.5rem 0.7rem;background:rgba(255,0,110,0.08);'
            'border:1px solid rgba(255,0,110,0.30);border-radius:10px;'
            'font-size:0.85rem;">'
            '<span style="width:8px;height:8px;background:#ff006e;'
            'border-radius:50%;box-shadow:0 0 8px #ff006e"></span>'
            'API <strong>offline</strong></div>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Lottie loader (optional — won't break if streamlit-lottie missing)
# ---------------------------------------------------------------------------

def lottie(url_or_dict, *, height: int = 160, key: str | None = None) -> None:
    """Render a Lottie animation. Silently no-ops if streamlit-lottie isn't
    installed or the URL fails — never break the page over decoration."""
    try:
        from streamlit_lottie import st_lottie  # type: ignore
        import urllib.request

        if isinstance(url_or_dict, str):
            try:
                with urllib.request.urlopen(url_or_dict, timeout=4) as resp:
                    payload = json.loads(resp.read())
            except Exception:
                return
        else:
            payload = url_or_dict
        st_lottie(payload, height=height, key=key)
    except Exception:
        return
