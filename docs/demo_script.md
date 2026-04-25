# NEXUS-HEAL — 3-Minute Demo Script

A click-by-click walkthrough that lands the milestone story in roughly
three minutes. Time-budget cues are in `[brackets]`. Total ≈ 3:00.

## Pre-flight (do this before the professor walks in)

1. Open two terminals in the project root.
2. Terminal 1 — `python main.py` (FastAPI on `:8000`, Telegram bot polling).
3. Terminal 2 — `streamlit run ui/app.py` (Streamlit on `:8501`).
4. Terminal 3 (one-shot) — `python -m demo.preload` to seed 4 alerts so
   Mission Control isn't empty when the page loads.
5. Have these tabs open in the browser:
   - **Mission Control** (`http://localhost:8501`)
   - The repo on GitHub (so you can show commits if asked)
   - Optional: `http://localhost:8000/alerts` (raw API output for credibility)

If `GROQ_API_KEY` is on its daily TPD limit, switch to the 8B model
beforehand by exporting `LLM_MODEL=llama-3.1-8b-instant` in terminal 1
*before* starting `python main.py`. Quality dips a bit; the demo still works.

---

## The 3-minute walkthrough

### [0:00 — 0:30]  Mission Control — the system at a glance

> *"This is NEXUS-HEAL — a multi-agent self-healing infra system. Four agents
> in a LangGraph pipeline behind a FastAPI server, with a Telegram bot and a
> Streamlit dashboard on top."*

- Land on **Mission Control**. The KPI cards show alerts processed,
  critical/high split, average diagnosis confidence, fixes executed.
- Point at the alert grid. *"Each card is one full pipeline run — Sentinel
  classified it, Maven retrieved the runbook, Healer planned the fix,
  Watcher executed the safe verifications."*

### [0:30 — 1:30]  Submit Alert — the live pipeline

> *"Let's run a real alert end-to-end."*

- Click **Submit Alert** in the sidebar.
- Click the **🔥 CPU spike** preset — populates the textarea.
- Click **Analyze alert**.
- Watch the four-stage pipeline glow: *"Sentinel is classifying… Maven is
  hitting ChromaDB and the LLM… Healer is generating the fix plan… Watcher
  is preparing for execution."*
- When the result arrives, point at:
  - The **classification** card (alert type + severity badge)
  - The **confidence gauge** *("blended from LLM self-assessment, RAG
    retrieval quality, and alert specificity")*
  - The **fix plan** + **fix commands** *("the Healer produced these from
    the runbook, not hardcoded")*

### [1:30 — 2:30]  Approve & execute — the killer moment

> *"Now the part that's new in Milestone 3 — the Watcher used to simulate
> execution. We made it real."*

- Click **Approve & execute**.
- Scroll to the **Watcher execution log**:
  > *"Each fix command was classified into safe / mutation / unknown. Safe
  > read-only commands — `kubectl get`, `df -h`, `curl -I` — actually ran
  > via subprocess and you can see the captured stdout right here. Mutation
  > commands like `kubectl delete` or `systemctl restart` are gated for
  > human review — we never auto-execute LLM-generated mutations."*
- Show the **Outcome** card on the right: *"X safe commands ran for real,
  Y mutation commands held for review."*

### [2:30 — 3:00]  Reliability story — the milestone highlight

> *"Two things I want to call out from the milestone report."*

- Open `docs/reliability_findings.md` (or summarise verbally):
  - *"We built an LLM-as-judge groundedness check. It returned 15 % on the
    first run. We traced it to a leak — the Maven prompt was exposing the
    RAG similarity score to the LLM, and the LLM was repeating it as a
    factual claim in the diagnosis. A two-line prompt fix took it to 60 %
    on the binary judge, and 70-80 % on the rubric judge. The retrieval
    metrics couldn't have caught it — that's why reliability checks are
    necessary, not optional."*
- Open `docs/milestone3_matrix.md`:
  - *"Every M2 row delivered, every M3 row delivered. Zero partial."*

---

## Likely questions and short answers

- **"Does it actually execute?"** → *"Read-only verifications run for real;
  mutations are gated. That's deliberate — auto-running unreviewed LLM
  shell commands in production would be reckless. The matrix flags this
  honestly: real read-only execution shipped, full mutation execution with
  RBAC scoping is logged as future work."*
- **"How did you pick chunk=500 / overlap=50?"** → *"Section-length
  measurement on the runbooks: median 272 chars, max 510, zero sections
  over 600. chunk=500 keeps each retrievable unit aligned to a single
  section."*
- **"Why not a stronger embedding?"** → *"We tried. ST MiniLM gives
  identical scores to ONNX MiniLM (proves the quantization is lossless).
  BGE-small actually underperforms on our corpus — minus 3.7 points at the
  selected config. ONNX MiniLM is the right answer on quality AND
  dependency weight."*
- **"What's left to build?"** → *"One High priority — hybrid BM25 + dense
  retrieval, to fix queries with no domain keywords (current ceiling).
  Everything else is polish."*

## Recovery cues if something breaks

- **API offline** — the sidebar pill turns magenta. Restart `python main.py`.
- **Pipeline stuck** — Groq TPD is exhausted. Set
  `export LLM_MODEL=llama-3.1-8b-instant` and restart `python main.py`.
- **Empty dashboard** — `python -m demo.preload --approve` to seed and
  approve four alerts at once.
