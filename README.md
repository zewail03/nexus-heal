<div align="center">

# 🛡️  NEXUS-HEAL

**Network Expert Unified System for Healing, Error-Analysis & Logging**

A multi-agent self-healing infrastructure agent — Sentinel → Maven → Healer → Watcher,
running on LangGraph, Groq Llama 3.3, ChromaDB, FastAPI, Streamlit, Telegram, and n8n.

[![Tests](https://github.com/zewail03/nexus-heal/actions/workflows/watcher-tests.yml/badge.svg)](https://github.com/zewail03/nexus-heal/actions/workflows/watcher-tests.yml)
![Python](https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white)
![LLM](https://img.shields.io/badge/LLM-Groq%20%E2%80%A2%20Llama%203.3%2070B-F55036)
![RAG](https://img.shields.io/badge/RAG-ChromaDB%20%2B%20MiniLM-46AC93)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

</div>

---

## What it does

A monitoring alert hits the API. Four agents process it in sequence:

1. **🧭 Sentinel** — classifies the alert into one of 10 known incident types (CPU spike, memory leak, DB connection, …) with calibrated confidence.
2. **📚 Maven** — retrieves the top-3 most relevant runbook chunks from ChromaDB (cosine, 384-d MiniLM embeddings) and asks Llama 3.3 70B for a root cause and diagnosis. Re-runs itself if confidence < 0.5.
3. **🔧 Healer** — generates a 3–5 step fix plan, concrete shell/`kubectl` commands, and a rollback plan.
4. **🛡️ Watcher** — classifies each fix command into **safe** (read-only verifications: `kubectl get`, `df -h`, `curl -I`, …) and **mutation** (destructive: `kubectl delete`, `rm`, `systemctl restart`, …). Safe commands run for real via `subprocess`; mutations are gated for human review. The validation report is built from real captured stdout, not a hard-coded success string.

A human approves or rejects through Telegram inline buttons or the Streamlit dashboard.

```
Alert source (n8n / Telegram / UI / curl)
        │
        ▼
   ┌──────────────────┐
   │  FastAPI server  │
   └────────┬─────────┘
            │
            ▼
   ╔═══════════════════════════════════════════════════════════╗
   ║  LangGraph StateGraph                                     ║
   ║                                                           ║
   ║   Sentinel ──▶ Maven ──▶ Healer ──▶ Watcher ──▶ END       ║
   ║                  ▲ │                                      ║
   ║                  └─┘  retry if confidence < 0.5 (≤ 2x)    ║
   ╚═══════════════════════════════════════════════════════════╝
```

---

## Quick start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Copy and edit .env (Groq + Telegram keys, all free tier)
cp .env.example .env

# 3. Run the API + Telegram bot
python main.py

# 4. Run the dashboard (separate terminal)
streamlit run ui/app.py

# 5. Seed the dashboard with 4 demo alerts (separate terminal)
python -m demo.preload --approve
```

Open **http://localhost:8501** for the dashboard, or message the Telegram bot:
- `/demo` — run a built-in CPU-spike alert
- `/alert <text>` — run a custom alert

---

## Milestone 3 highlights

This milestone added a full retrieval-quality and reliability evaluation
harness, plus a real (safety-allowlisted) Watcher.

| Layer | What we measured | Result |
|---|---|---|
| Retrieval | Hit@3 on 40 hand-labeled queries | **0.950** |
| Retrieval | MRR | **0.890** |
| Reliability | Context relevance (mean / % ≥ 0.7) | **0.78** / **91.7 %** |
| Reliability | Groundedness — binary 70B (after fix) | **15 % → 60 %** |
| Reliability | Groundedness — rubric N=3 (8B) | **0.90 mean** |
| Sweep | Configurations evaluated | **27** (3 embeddings × 9 chunk/overlap) |
| Tests | pytest suite (deterministic + e2e) | **48 total**, 42 deterministic in ~2 s |
| Watcher | Safe commands run for real, mutations gated | ✅ |
| Knowledge base | Runbooks ingested into ChromaDB | **26** (post-stretch — was 10) |
| Persistence | Alert store survives server restart | SQLite-backed `AlertStore` |

## Final milestone — three retrievers, every M3 ceiling closed

Three retrievers, each evaluated on the **same 40 labeled queries and
KB-26** used for the M3 headline number:

| Metric | `dense` | `hybrid` (production) | `query_rewrite_hybrid` |
|---|---|---|---|
| Hit@1 | 0.725 | **0.750** | 0.675 |
| Hit@3 | 0.800 | 0.850 | **0.900** |
| Hit@5 | 0.875 | 0.900 | **0.925** |
| MRR | 0.7717 | **0.8058** | 0.7842 |
| **Hard Hit@3** | 0.500 | 0.500 | **0.800** |
| **Hard MRR** | 0.4783 | 0.5200 | **0.6667** |

- **`hybrid`** ([rag/hybrid_retriever.py](rag/hybrid_retriever.py)) fuses
  BM25 and dense cosine via Reciprocal Rank Fusion (k = 60). Now the
  production retriever — [agents/maven.py](agents/maven.py) imports
  `hybrid_retrieve` directly. Closes the High-priority M3 Future-Work
  item.
- **`query_rewrite_hybrid`** ([rag/query_rewriter.py](rag/query_rewriter.py))
  calls Groq Llama 3.3 70B to expand colloquial queries into keyword
  form, then runs hybrid. Closes the **named M3 ceiling Q07** —
  *"Service becomes unresponsive after running for a day, a manual
  restart fixes it temporarily"* — flipping MRR 0.00 → 1.00 by
  expanding "unresponsive + manual restart" into
  `memory_leak OOM heap RSS GC SIGKILL exit code 137`.
- **70B rubric re-judge** also shipped this milestone. The 8B
  rubric's lenient 0.90 is replaced with the strict 70B 0.50,
  validating the binary judge's 60 % as the lower bound and
  tightening the best-estimate band to 50 – 60 %.

Honest tradeoff: query-rewrite Hit@1 regresses 0.75 → 0.68 because
expansion adds noise to already-keyword-rich queries. Recommended use
is as a confidence-low Maven retry path, not as a default.

Full numbers, per-query case studies, and the production-switch
narrative in [`docs/hybrid_retrieval.md`](docs/hybrid_retrieval.md).

The retrieval-quality eval surfaced a real bug — the Maven prompt was
leaking RAG similarity scores into diagnoses, which the LLM then
quoted as if they were clinical evidence. A two-line fix took
groundedness from 15 % to 60 % on the binary judge. Full story in
[`docs/reliability_findings.md`](docs/reliability_findings.md).

---

## Documentation

| Doc | Purpose |
|---|---|
| [`docs/milestone3_report.md`](docs/milestone3_report.md) | Full milestone report (planned vs delivered, retrieval quality, reliability, correctness, future work) |
| [`docs/milestone3_matrix.md`](docs/milestone3_matrix.md) | Planned vs delivered matrix — 11/11 M2, 10/10 M3, zero partial |
| [`docs/hybrid_retrieval.md`](docs/hybrid_retrieval.md) | Final-milestone deliverable — RRF fusion of BM25 + dense, before/after numbers, per-query case studies |
| [`docs/reliability_findings.md`](docs/reliability_findings.md) | Prompt-leak bug story — caught by the LLM-as-judge groundedness check |
| [`docs/demo_script.md`](docs/demo_script.md) | 3-minute click-by-click demo walkthrough |
| [`eval/results/design_choices.md`](eval/results/design_choices.md) | Embedding + chunk + overlap choice with full sweep evidence |

---

## Project structure

```
nexus-heal/
├── agents/
│   ├── state.py              # LangGraph shared state (TypedDict)
│   ├── sentinel.py           # Agent 1: alert classifier (LLM)
│   ├── maven.py              # Agent 2: RAG + LLM diagnoser
│   ├── healer.py             # Agent 3: fix-plan + commands generator
│   └── watcher.py            # Agent 4: safety allowlist + real subprocess execution
├── graph/
│   └── pipeline.py           # LangGraph StateGraph wiring + retry edge
├── rag/
│   ├── vectorstore.py        # ChromaDB ingest (chunk=500/overlap=50)
│   └── retriever.py          # cosine top-k query
├── knowledge_base/           # 26 runbook markdown files (10 M2 + 16 M3-stretch)
├── api/
│   ├── server.py             # FastAPI: /analyze, /approve, /alerts, /health
│   └── storage.py            # SQLite AlertStore — survives server restart
├── bot/telegram_bot.py       # Telegram bot — /alert, /demo, Approve/Reject buttons
├── n8n/nexus_heal_workflow.json
├── ui/
│   ├── app.py                # Streamlit dashboard (Mission Control / Submit / Graph / RAG Debug)
│   ├── components.py         # Animated pipeline, gauges, score bars, terminal
│   └── styles.py             # Dark neon glassmorphism theme
├── eval/
│   ├── labeled_queries.json           # 40 queries × 4 difficulty levels
│   ├── retrieval_metrics.py           # Hit@k / Precision@k / Recall@k / MRR / NDCG
│   ├── sweep.py                       # 27-config hyperparameter sweep
│   ├── reliability_context.py         # LLM-as-judge: per-chunk relevance
│   ├── reliability_groundedness.py    # LLM-as-judge: binary {0, 1}
│   ├── reliability_groundedness_rubric.py  # 3-level rubric, N=3 majority vote
│   └── results/                       # All CSVs + JSON summaries + design_choices.md
├── tests/
│   ├── test_e2e.py           # FastAPI + graph integration (needs Groq)
│   ├── test_watcher.py       # 30 deterministic safety-allowlist tests
│   ├── test_storage.py       # 12 deterministic SQLite AlertStore tests
│   └── conftest.py
├── demo/preload.py           # Seed the dashboard with 4 alerts
├── docs/                     # Milestone report, matrix, reliability story, demo script
├── config.py                 # Loads .env; LLM_MODEL is env-overridable
├── main.py                   # Entry point — boots vectorstore + FastAPI + Telegram
└── requirements.txt
```

---

## Tech stack

| Component | Technology |
|---|---|
| Multi-agent framework | LangGraph (StateGraph + conditional edges) |
| LLM | Groq Llama 3.3 70B (default) — switchable via `LLM_MODEL=` env |
| RAG vector store | ChromaDB (cosine, 384-d MiniLM ONNX) |
| Retrieval embedding | `all-MiniLM-L6-v2` (ONNX-quantized; ST + BGE-small benchmarked, both rejected — see `design_choices.md`) |
| API server | FastAPI + Uvicorn |
| Frontend | Streamlit + Plotly (radial gauges) + custom CSS theme |
| Chat bot | `python-telegram-bot` |
| Workflow automation | n8n |
| Tests | pytest (36 tests; 30 deterministic) |

---

## Reproducing the eval

```bash
# Retrieval metrics (40 queries against the production ChromaDB)
python -m eval.retrieval_metrics --name baseline

# Full 27-config sweep (chunk × overlap × embedding) — needs sentence-transformers
pip install sentence-transformers
python -m eval.sweep

# Reliability checks (LLM-as-judge — needs Groq tokens)
python -m eval.reliability_context
python -m eval.reliability_groundedness
python -m eval.reliability_groundedness_rubric

# Tests
python -m pytest tests/ -v
```

---



Built at **Al Alamein University**.
