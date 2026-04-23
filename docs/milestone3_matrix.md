# Planned vs. Delivered — Milestone 3 Matrix

Legend: ✅ delivered · ⚠️ partial / delivered with caveat · ❌ not delivered

## Milestone 2 scope (carried forward)

| Planned feature | Delivered? | Evidence / file | Notes |
|---|---|---|---|
| Real LangGraph StateGraph with 4 agents | ✅ | [graph/pipeline.py](../graph/pipeline.py) | `build_graph()` wires Sentinel → Maven → Healer → Watcher → END. Singleton `nexus_graph` imported by API and bot. |
| Conditional retry edge on Maven (confidence < 0.5) | ✅ | [graph/pipeline.py::should_retry](../graph/pipeline.py) | Uses `MIN_CONFIDENCE_THRESHOLD=0.5`, capped by `MAX_ITERATIONS=2` to avoid infinite loops. Verified by inspecting the edge definition in `add_conditional_edges`. |
| RAG with ChromaDB + 10 runbooks | ✅ | [rag/vectorstore.py](../rag/vectorstore.py), [knowledge_base/](../knowledge_base/) | 10 runbook markdown files ingested into ChromaDB with cosine similarity; 48 chunks total with chunk=500/overlap=50. |
| FastAPI `/analyze` endpoint | ✅ | [api/server.py](../api/server.py) | Endpoints: `POST /analyze`, `POST /approve/{alert_id}`, `GET /alerts`, `GET /health`. Verified by pytest + TestClient. |
| Telegram bot with `/alert`, `/demo`, Approve/Reject | ✅ | [bot/telegram_bot.py](../bot/telegram_bot.py) | Also ships `/start` and `/status`. Approve/Reject are inline `CallbackQueryHandler` buttons that POST to `/approve/{id}`. |
| n8n workflow (Webhook → API → Telegram) | ✅ | [n8n/nexus_heal_workflow.json](../n8n/nexus_heal_workflow.json) | Importable into any n8n instance. |
| Streamlit dashboard | ✅ | [ui/app.py](../ui/app.py) | Four tabs: Dashboard, Submit Alert, Agent Graph (Graphviz), RAG Debug. |
| Human-in-the-loop approval | ✅ | [bot/telegram_bot.py](../bot/telegram_bot.py), [agents/watcher.py](../agents/watcher.py) | Approve/Reject drives Watcher's `execution_status` branch. Default (no approval) lands `rejected`, proving the gate works. |
| Groq + Llama 3.3 integration | ✅ | [config.py](../config.py), [agents/maven.py](../agents/maven.py) | Default model `llama-3.3-70b-versatile`. Now env-overridable via `LLM_MODEL` (added in M3 for reliability re-runs when 70B TPD exhausted). |
| Fix execution with rollback | ⚠️ partial | [agents/healer.py](../agents/healer.py), [agents/watcher.py](../agents/watcher.py) | Healer *generates* `fix_plan`, `fix_commands`, and `rollback_plan` fields. Watcher **simulates** execution rather than running the commands — it reports success without touching a real shell / kubectl. This is an intentional safety choice but worth flagging. |
| Knowledge base expansion (5 → 10+) | ✅ | [knowledge_base/](../knowledge_base/) | 10 runbooks, covering CPU, memory, disk, DB, network, SSL, API timeout, pod crash, queue, auth. |

## Milestone 3 — new work

| New deliverable | Delivered? | Evidence / file | Notes |
|---|---|---|---|
| 40-query labeled eval set | ✅ | [eval/labeled_queries.json](../eval/labeled_queries.json) | 4 queries × 10 runbooks × 4 difficulty levels (easy / medium / hard / composite). Hard queries are intentionally adversarial and documented as such in `_meta.hard_queries_note`. |
| Retrieval metrics harness (Hit@k, P@k, R@k, MRR, NDCG) | ✅ | [eval/retrieval_metrics.py](../eval/retrieval_metrics.py) | Outputs per-query CSV + aggregate JSON. Runbook-level dedup on NDCG to keep scores bounded. `--name` flag supports side-by-side runs (`baseline` vs `final`). |
| Design-choice sweep (9 configs) | ✅ | [eval/sweep.py](../eval/sweep.py), [eval/results/sweep_results.csv](../eval/results/sweep_results.csv), [eval/results/design_choices.md](../eval/results/design_choices.md) | Swept `chunk_size ∈ {300, 500, 800}` × `overlap ∈ {0, 50, 100}`. Wall-clock per config recorded. Winning config explained with section-length evidence (median 272 chars). |
| Embedding comparison (MiniLM-ONNX vs sentence-transformers) | ⚠️ partial | [eval/sweep.py](../eval/sweep.py) | Skipped sentence-transformers install (~2 GB torch download violates "no new heavy deps" constraint). Used Chroma's ONNX-quantized MiniLM. Rationale documented in [eval/results/design_choices.md](../eval/results/design_choices.md) § "Why ONNX-quantized MiniLM". Logged as future work. |
| Context relevance check (LLM-as-judge) | ✅ | [eval/reliability_context.py](../eval/reliability_context.py), [eval/results/context_relevance.csv](../eval/results/context_relevance.csv) | 40 queries × 3 chunks = 120 judge calls on 70B. Mean 0.78, 91.67 % of chunks ≥ 0.7. |
| Groundedness check (LLM-as-judge) | ✅ | [eval/reliability_groundedness.py](../eval/reliability_groundedness.py), [eval/results/groundedness.csv](../eval/results/groundedness.csv) | 20 stratified queries (5 per difficulty), full pipeline + judge. Caught prompt-leak bug; see [reliability_findings.md](reliability_findings.md). |
| End-to-end pytest suite | ✅ | [tests/test_e2e.py](../tests/test_e2e.py), [tests/conftest.py](../tests/conftest.py) | 5 tests (4 parametrized HTTP + 1 direct graph). All passing in ~33s. `pytest` added to [requirements.txt](../requirements.txt). |
| Maven prompt-leak fix | ✅ | [agents/maven.py](../agents/maven.py) | Reliability check surfaced it; 2-line prompt fix applied and re-measured. 15 % → 58.82 % groundedness. Documented in [reliability_findings.md](reliability_findings.md). |
| Reliability re-verification on 70B | ⚠️ pending | — | After-fix re-run had to use 8B due to 70B daily token quota exhaustion. Clean 70B re-run is queued for the next TPD reset. 8B caveat disclosed throughout the report. |

## Summary

- **11 / 11** Milestone 2 rows delivered; one (`Fix execution with rollback`) ships as intentionally simulated, not real — called out explicitly.
- **7 / 9** Milestone 3 rows fully delivered; two are `⚠️ partial`:
  - Embedding comparison limited to ONNX MiniLM (torch install skipped by design)
  - Reliability re-verification ran on 8B, not 70B (daily-quota ceiling; directional result valid)
- No row is `❌ not delivered`.
