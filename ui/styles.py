"""
NEXUS-HEAL — central CSS theme.

A dark, neon-accent, glassmorphism look. All app-wide styling lives
here so individual pages stay declarative.

Colour palette
--------------
    --nx-bg-deep      #050814   page background
    --nx-bg-panel     #0d1224   card / panel background
    --nx-bg-elevated  #131a30   sidebar / hovered cards
    --nx-cyan         #00d4ff   primary accent (info, active)
    --nx-magenta      #ff006e   destructive / critical
    --nx-orange       #fb5607   warning / high severity
    --nx-yellow       #ffbe0b   medium severity
    --nx-lime         #b2ff59   success / low severity
    --nx-purple       #8338ec   secondary accent
    --nx-text         #e6e8f0   foreground
    --nx-text-dim     #8b91a9   muted foreground
"""
from __future__ import annotations

import streamlit as st


_CSS = """
<style>
:root {
    --nx-bg-deep: #050814;
    --nx-bg-panel: #0d1224;
    --nx-bg-elevated: #131a30;
    --nx-cyan: #00d4ff;
    --nx-magenta: #ff006e;
    --nx-orange: #fb5607;
    --nx-yellow: #ffbe0b;
    --nx-lime: #b2ff59;
    --nx-purple: #8338ec;
    --nx-text: #e6e8f0;
    --nx-text-dim: #8b91a9;
    --nx-border: rgba(0, 212, 255, 0.18);
}

/* -- Page chrome ------------------------------------------------------- */
[data-testid="stAppViewContainer"], [data-testid="stHeader"] {
    background:
        radial-gradient(1200px 600px at 10% -10%, rgba(0, 212, 255, 0.10), transparent 60%),
        radial-gradient(900px 600px at 100% 0%, rgba(131, 56, 236, 0.10), transparent 55%),
        radial-gradient(800px 800px at 50% 100%, rgba(255, 0, 110, 0.06), transparent 55%),
        var(--nx-bg-deep) !important;
}

[data-testid="stHeader"] {
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--nx-border);
}

[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #08102a 0%, #050814 100%) !important;
    border-right: 1px solid var(--nx-border);
}

[data-testid="stSidebar"] * {
    color: var(--nx-text) !important;
}

/* -- Typography -------------------------------------------------------- */
html, body, [data-testid="stAppViewContainer"] *:not(code):not(pre) {
    font-family: "Inter", "Segoe UI", system-ui, sans-serif !important;
    color: var(--nx-text);
}

/* Streamlit uses Material Symbols icons for chevrons / sidebar collapse /
   status pills. The font is fetched from Google Fonts at runtime; when
   that fetch fails (offline, corp proxy, blocked CDN) the ligature can't
   resolve and the literal icon name leaks as text — e.g.
   "keyboard_double_arrow_right" overlapping the expander label.
   Hide these icon containers entirely; they are decorative, the app
   functions identically without them. */
[class*="material-symbols"],
[class*="material-icons"],
[class*="MaterialIcons"],
[data-testid="stIconMaterial"],
[data-testid="stExpanderIcon"],
[data-testid="stMarkdownContainer"] [class*="material-symbols"],
[data-testid="stExpander"] svg + span,
[data-testid="stExpander"] span[class*="symbols"],
.material-symbols-outlined,
.material-symbols-rounded,
.material-symbols-sharp,
.material-icons,
.material-icons-outlined,
.material-icons-round,
span[class*="symbols"],
span[class*="Icon"],
i[class*="material"] {
    display: none !important;
    font-size: 0 !important;
    width: 0 !important;
    height: 0 !important;
    visibility: hidden !important;
    text-indent: -99999px !important;
    overflow: hidden !important;
    color: transparent !important;
    margin: 0 !important;
    padding: 0 !important;
}

/* Defensive — any element whose visible text starts with the leaked
   icon-name pattern (lowercase + underscores like "keyboard_double_*")
   gets pushed off-screen. Catches anything the class selectors miss. */
[data-testid="stExpander"] summary > span:first-child:not(:has(*)) {
    text-indent: -99999px !important;
    width: 0 !important;
    overflow: hidden !important;
    display: inline-block !important;
}

h1, h2, h3, h4 {
    letter-spacing: -0.01em;
    font-weight: 700 !important;
}

h1 {
    background: linear-gradient(90deg, #fff 0%, var(--nx-cyan) 60%, var(--nx-purple) 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    color: transparent !important;
    font-size: 2.4rem !important;
}

/* -- Cards / containers ----------------------------------------------- */
.nx-card {
    background: linear-gradient(135deg,
        rgba(13, 18, 36, 0.80) 0%,
        rgba(19, 26, 48, 0.65) 100%);
    border: 1px solid var(--nx-border);
    border-radius: 16px;
    padding: 1.25rem 1.5rem;
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.04) inset,
        0 12px 32px rgba(0, 0, 0, 0.35);
    transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}
.nx-card:hover {
    transform: translateY(-2px);
    border-color: rgba(0, 212, 255, 0.32);
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.06) inset,
        0 12px 32px rgba(0, 0, 0, 0.42),
        0 0 30px rgba(0, 212, 255, 0.08);
}

.nx-card-title {
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.18em;
    color: var(--nx-text-dim);
    margin-bottom: 0.4rem;
}
.nx-card-value {
    font-size: 2rem;
    font-weight: 700;
    color: var(--nx-text);
}
.nx-card-sub {
    font-size: 0.85rem;
    color: var(--nx-text-dim);
}

/* -- Severity / status badges ----------------------------------------- */
.nx-badge {
    display: inline-block;
    padding: 0.18rem 0.7rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.nx-badge.critical { background: rgba(255, 0, 110, 0.15);  color: var(--nx-magenta); border: 1px solid rgba(255, 0, 110, 0.45); animation: pulse-magenta 2s ease-in-out infinite; }
.nx-badge.high     { background: rgba(251, 86, 7, 0.15);   color: var(--nx-orange);  border: 1px solid rgba(251, 86, 7, 0.45); }
.nx-badge.medium   { background: rgba(255, 190, 11, 0.15); color: var(--nx-yellow);  border: 1px solid rgba(255, 190, 11, 0.45); }
.nx-badge.low      { background: rgba(178, 255, 89, 0.15); color: var(--nx-lime);    border: 1px solid rgba(178, 255, 89, 0.45); }
.nx-badge.info     { background: rgba(0, 212, 255, 0.15);  color: var(--nx-cyan);    border: 1px solid rgba(0, 212, 255, 0.45); }
.nx-badge.muted    { background: rgba(139, 145, 169, 0.12);color: var(--nx-text-dim);border: 1px solid rgba(139, 145, 169, 0.30); }

@keyframes pulse-magenta {
    0%, 100% { box-shadow: 0 0 0 0 rgba(255, 0, 110, 0.45); }
    50%      { box-shadow: 0 0 14px 3px rgba(255, 0, 110, 0.20); }
}

/* -- Animated pipeline nodes ------------------------------------------ */
.nx-pipeline {
    display: flex;
    gap: 0.6rem;
    align-items: stretch;
    margin: 0.75rem 0 1.25rem 0;
    flex-wrap: nowrap;
}
.nx-stage {
    flex: 1;
    min-width: 0;
    background: rgba(13, 18, 36, 0.80);
    border: 1px solid var(--nx-border);
    border-radius: 14px;
    padding: 0.75rem 0.9rem;
    position: relative;
    overflow: hidden;
    transition: all 0.25s ease;
}
.nx-stage .stage-label {
    font-size: 0.68rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--nx-text-dim);
    margin-bottom: 0.25rem;
}
.nx-stage .stage-name {
    font-weight: 700;
    font-size: 1.05rem;
    color: var(--nx-text);
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.nx-stage .stage-icon {
    font-size: 1.1rem;
    margin-right: 0.4rem;
    opacity: 0.9;
}
.nx-stage.idle    { opacity: 0.55; }
.nx-stage.running {
    border-color: var(--nx-cyan);
    box-shadow: 0 0 24px rgba(0, 212, 255, 0.30), 0 0 0 1px rgba(0, 212, 255, 0.45) inset;
    animation: stage-pulse 1.4s ease-in-out infinite;
}
.nx-stage.done {
    border-color: rgba(178, 255, 89, 0.55);
    box-shadow: 0 0 18px rgba(178, 255, 89, 0.18) inset;
}
.nx-stage.error {
    border-color: rgba(255, 0, 110, 0.55);
    box-shadow: 0 0 18px rgba(255, 0, 110, 0.20) inset;
}
.nx-stage.done .check {
    color: var(--nx-lime);
    font-weight: 800;
}
.nx-stage.running .spin {
    display: inline-block;
    color: var(--nx-cyan);
    animation: spin 1s linear infinite;
}
@keyframes stage-pulse {
    0%, 100% { box-shadow: 0 0 24px rgba(0, 212, 255, 0.30), 0 0 0 1px rgba(0, 212, 255, 0.45) inset; }
    50%      { box-shadow: 0 0 38px rgba(0, 212, 255, 0.45), 0 0 0 1px rgba(0, 212, 255, 0.70) inset; }
}
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

.nx-arrow {
    flex: 0 0 auto;
    align-self: center;
    color: var(--nx-text-dim);
    font-size: 1.1rem;
    margin: 0 -0.1rem;
    user-select: none;
}

/* -- Score bars (RAG retrieval) --------------------------------------- */
.nx-bar-row {
    display: grid;
    grid-template-columns: 110px 1fr 60px;
    gap: 0.75rem;
    align-items: center;
    margin: 0.4rem 0;
}
.nx-bar-label {
    font-size: 0.78rem;
    color: var(--nx-text-dim);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.nx-bar-track {
    height: 8px;
    background: rgba(255, 255, 255, 0.06);
    border-radius: 999px;
    overflow: hidden;
}
.nx-bar-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--nx-cyan), var(--nx-purple));
    border-radius: 999px;
    transition: width 0.6s cubic-bezier(0.22, 1, 0.36, 1);
    box-shadow: 0 0 12px rgba(0, 212, 255, 0.35);
}
.nx-bar-value {
    font-variant-numeric: tabular-nums;
    color: var(--nx-text);
    font-weight: 600;
    font-size: 0.9rem;
}

/* -- Terminal-style output (Watcher) ---------------------------------- */
.nx-terminal {
    background: #02050d;
    border: 1px solid rgba(0, 212, 255, 0.25);
    border-radius: 14px;
    padding: 1rem 1.1rem;
    font-family: "JetBrains Mono", "Cascadia Code", "Consolas", monospace !important;
    font-size: 0.86rem;
    line-height: 1.55;
    color: #d6e6ff;
    box-shadow: 0 0 22px rgba(0, 212, 255, 0.08) inset;
    max-height: 320px;
    overflow-y: auto;
}
.nx-terminal-line.exec   { color: var(--nx-lime); }
.nx-terminal-line.fail   { color: var(--nx-orange); }
.nx-terminal-line.gated  { color: var(--nx-yellow); }
.nx-terminal-line.unknown{ color: var(--nx-text-dim); }
.nx-terminal-cmd { color: var(--nx-cyan); font-weight: 600; }
.nx-terminal-stdout { color: #98a8c4; padding-left: 1.2rem; opacity: 0.85; }

/* Hide Streamlit's default running indicator since we have our own */
[data-testid="stStatusWidget"] { display: none; }

/* Make the default sidebar nav titles nicer */
[data-testid="stSidebarNav"] { display: none; }

/* Tighten Streamlit metric padding */
[data-testid="stMetric"] {
    background: rgba(13, 18, 36, 0.65);
    border: 1px solid var(--nx-border);
    border-radius: 14px;
    padding: 0.85rem 1rem;
    backdrop-filter: blur(6px);
}
[data-testid="stMetricValue"] {
    color: var(--nx-text) !important;
    font-size: 1.6rem !important;
}
[data-testid="stMetricLabel"] p {
    color: var(--nx-text-dim) !important;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.72rem !important;
}

/* Buttons */
button[kind="primary"], .stButton > button {
    background: linear-gradient(135deg, var(--nx-cyan), var(--nx-purple)) !important;
    color: #fff !important;
    border: none !important;
    font-weight: 600 !important;
    padding: 0.55rem 1.1rem !important;
    border-radius: 12px !important;
    box-shadow: 0 6px 18px rgba(0, 212, 255, 0.25);
    transition: transform 0.12s ease, box-shadow 0.12s ease;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 10px 26px rgba(0, 212, 255, 0.40);
}

/* Expanders */
[data-testid="stExpander"] {
    background: rgba(13, 18, 36, 0.65);
    border: 1px solid var(--nx-border);
    border-radius: 14px;
    backdrop-filter: blur(6px);
}

/* Progress bars get the cyan-purple gradient */
[data-testid="stProgress"] > div > div > div > div {
    background: linear-gradient(90deg, var(--nx-cyan), var(--nx-purple)) !important;
}

/* Code blocks */
code, pre, [data-testid="stCode"] {
    background: #02050d !important;
    border: 1px solid var(--nx-border) !important;
    border-radius: 10px !important;
    color: #d6e6ff !important;
}
</style>
"""


def inject() -> None:
    """Apply the NEXUS-HEAL theme. Call once near the top of every page."""
    st.markdown(_CSS, unsafe_allow_html=True)
