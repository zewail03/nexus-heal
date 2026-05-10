# NEXUS-HEAL — agent guide

University capstone project (Al Alamein University). Multi-agent
self-healing infrastructure system. Read this first before making
non-trivial changes.

## What it is

LangGraph StateGraph: `Sentinel → Maven ⇄(retry if conf<0.5, ≤2 iters)→ Healer → Watcher → END`.
Wired up in [graph/pipeline.py](graph/pipeline.py); agents in [agents/](agents/).

| Agent | Role | LLM | RAG |
|---|---|---|---|
| Sentinel | Classify alert into one of 26 types + severity | Groq Llama 3.3 70B | — |
| Maven | RAG-grounded diagnosis | Groq Llama 3.3 70B | hybrid retriever (production) |
| Healer | Generate fix plan + commands + rollback | Groq Llama 3.3 70B | — |
| Watcher | Execute safe-allowlisted commands; gate mutations | — | — |

Surface: FastAPI on `:8000` (`/analyze`, `/approve`, `/alerts`, `/health`),
Streamlit dashboard on `:8501`, Telegram bot, n8n webhook.

## Project layout

```
agents/      Sentinel, Maven, Healer, Watcher + shared NexusState
graph/       LangGraph pipeline wiring + retry edge
rag/         retriever (dense), hybrid_retriever (RRF), query_rewriter (LLM expansion)
api/         FastAPI server + SQLite-backed AlertStore
ui/          Streamlit dashboard (4 tabs: Mission Control, Submit, Graph, RAG Debug)
bot/         python-telegram-bot
n8n/         workflow JSON — importable into any n8n instance
knowledge_base/  26 runbook markdown files
eval/        retrieval metrics, 27-config sweep, LLM-as-judge harness, results CSVs
tests/       48 pytest tests (42 deterministic + 6 e2e on Groq)
docs/        Milestone reports + matrix + reliability findings + hybrid retrieval write-up
demo/        preload.py — seed dashboard with demo alerts
```

## Retrievers — three modes

1. **`dense`** ([rag/retriever.py](rag/retriever.py)) — ChromaDB cosine
   alone. M3 baseline (Hit@3 = 0.80 on KB-26).
2. **`hybrid`** ([rag/hybrid_retriever.py](rag/hybrid_retriever.py)) —
   **production retriever**, imported by Maven. RRF (k=60) over BM25Okapi
   + dense. Pulls full dense ranking once per query so BM25-only hits
   carry real cosine. Hit@3 = 0.85 on KB-26.
3. **`query_rewrite_hybrid`** — Maven retry path only. When Maven's
   first pass returns `confidence_diagnose < 0.5`, the LangGraph edge
   re-invokes Maven, which detects `iteration_count > 0` and switches
   to `query_rewrite_hybrid_retrieve`. Pays one Groq call to expand
   the query into keyword form, then runs hybrid. Hard-bucket Hit@3
   0.50 → 0.80; closes the M3 named ceiling Q07.

Eval all three with `python -m eval.retrieval_metrics --retriever {dense,hybrid,query_rewrite_hybrid}`.

## Run it

```bash
# 1. Install (Python 3.13 is the dev install — see below)
pip install -r requirements.txt

# 2. .env must contain GROQ_API_KEY (and optionally TELEGRAM_*)
cp .env.example .env

# 3. Boot vectorstore + FastAPI + Telegram bot
python main.py

# 4. Streamlit dashboard (separate terminal)
streamlit run ui/app.py

# 5. One-shot orchestration runner (boots both, runs eval)
python run_all.py
```

## Test commands

```bash
# Deterministic suite — 55 tests, ~30 s, no Groq required
python -m pytest tests/test_watcher.py tests/test_storage.py tests/test_hybrid_retriever.py -q

# E2E suite — 6 tests, ~73 s, needs Groq + populated ChromaDB
python -m pytest tests/test_e2e.py -v

# Full suite
python -m pytest tests/ -v
```

## Maven confidence math — DO NOT SIMPLIFY

```python
calibrated = 0.40 * llm_confidence + 0.35 * avg_rag_score + 0.25 * specificity
```

The 40/35/25 blend is intentional — `MIN_CONFIDENCE_THRESHOLD=0.5`
gates the retry edge, and the math was tuned so LLM-only confidence
can't override poor RAG matches. See commit `66128ff` for the
narrative. Don't collapse it into "just use the LLM number."

## Watcher — mutations are gated by design

[agents/watcher.py](agents/watcher.py) classifies fix commands into
**safe** (read-only allowlist: `kubectl get`, `df -h`, `curl -I`,
`pg_isready`, `systemctl status`, …) and **mutation** (`rm`,
`kubectl delete`, `systemctl restart`, `DROP TABLE`, …). Safe
commands run for real via `subprocess.run`. Mutations are returned
in the API response as gated for manual review.

**Don't lift the mutation gate.** It's a deliberate safety choice —
auto-executing unreviewed LLM-generated mutations in production
would be reckless. The next step (RBAC + command-review UI) is
logged as Future Work but is engineering scope, not a correctness gap.

## Persistence

[api/storage.py](api/storage.py) is a SQLite-backed `AlertStore` (WAL
mode, JSON-serialised state). Survives FastAPI restarts. DB path is
env-overridable via `NEXUS_DB_PATH` so tests can use a tmp DB
([tests/conftest.py](tests/conftest.py) does this autouse).

`./nexus_alerts.db*` files are gitignored.

## Eval harness

40 hand-labeled queries × 4 difficulty buckets in
[eval/labeled_queries.json](eval/labeled_queries.json). Hard-bucket
queries are intentionally adversarial — see `_meta.hard_queries_note`.

```bash
python -m eval.retrieval_metrics --retriever hybrid --name kb26_hybrid
python -m eval.sweep                                   # 27-config sweep
python -m eval.reliability_context                     # LLM-as-judge: relevance
python -m eval.reliability_groundedness                # LLM-as-judge: binary
python -m eval.reliability_groundedness_rubric \
    --input eval/results/groundedness_after_fix_70b.csv \
    --suffix _70b                                      # rubric, N=3 majority
```

All results land under [eval/results/](eval/results/) and are checked
in for reproducibility.

## Don't-do list

- **Don't switch Maven back to plain dense retrieval.** Hybrid is
  production; the cosine backfill in `hybrid_retrieve` keeps it
  honest. The M3 numbers were measured with hybrid — going back
  would be a regression.
- **Don't simplify the 40/35/25 confidence blend** without checking
  with the project owner (Adham). It's tuned for the retry threshold.
- **Don't lift the Watcher mutation gate.** See above.
- **Don't add `_pending_alerts: dict` back as in-memory state.**
  AlertStore replaced it for a reason — Mission Control needs to
  survive a server restart.
- **Don't introduce new dense/native deps** (e.g. sentence-transformers,
  torch) into `requirements.txt`. They were deliberately kept optional
  because the ONNX MiniLM that ships with ChromaDB matches the
  full-precision ST MiniLM bit-for-bit on our corpus (see
  `eval/results/design_choices.md`).
- **Don't commit `nexus_alerts.db*`, `chroma_db/`, or
  `.run_all_logs/`** — they're gitignored for good reason.

## Environment notes (Windows dev box)

- **Use Python 3.13** for development (`c:/Users/adham/AppData/Local/Programs/Python/Python313/python.exe`).
  Python 3.12 on this box does NOT have `chromadb` installed.
- No `.venv` in the project — system Python 3.13 is the install.
- Shell is bash via Git Bash. PowerShell is also available.

## Where to read more

- [README.md](README.md) — public-facing project description
- [docs/milestone3_report.md](docs/milestone3_report.md) — full M3 report
- [docs/milestone3_matrix.md](docs/milestone3_matrix.md) — planned-vs-delivered
- [docs/hybrid_retrieval.md](docs/hybrid_retrieval.md) — final-milestone retrieval write-up
- [docs/reliability_findings.md](docs/reliability_findings.md) — prompt-leak bug story
- [eval/results/design_choices.md](eval/results/design_choices.md) — embedding/chunk/overlap rationale
