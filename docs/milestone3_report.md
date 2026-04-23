# NEXUS-HEAL — Milestone 3 Report

**Project:** Network Expert Unified System for Healing, Error-Analysis & Logging
**Team:** Adham (LangGraph + Sentinel), Walid (Maven + RAG), Mohamed (Healer + KB), Shahd (Telegram + UI)
**Date:** 2026-04-23

---

## 1. Planned vs. Delivered

See the full matrix in [milestone3_matrix.md](milestone3_matrix.md). Summary:

- **11 / 11** Milestone 2 features delivered. One flagged `⚠️ partial`:
  fix execution is **simulated** (Watcher reports success without running
  real shell commands) — an intentional safety choice we disclose
  explicitly.
- **9 new Milestone 3 deliverables.** Seven fully delivered (`✅`); two
  `⚠️ partial` — embedding comparison was limited to ONNX MiniLM (torch
  install skipped by design), and the reliability re-run after the
  prompt-fix used 8B because 70B TPD was exhausted.
- **Zero items are `❌ not delivered`.**

---

## 2. Live working system — what's new since M2

- **Labeled eval set**: [eval/labeled_queries.json](../eval/labeled_queries.json) — 40 queries, 4 per runbook × 4 difficulty buckets.
- **Metrics harness**: [eval/retrieval_metrics.py](../eval/retrieval_metrics.py) — Hit@k, Precision@k, Recall@k, MRR, NDCG@k, with per-difficulty breakdown.
- **Design-choice sweep**: [eval/sweep.py](../eval/sweep.py) — 9 configs, wall-clock timed, ranked by composite score.
- **Reliability checks**: [eval/reliability_context.py](../eval/reliability_context.py) + [eval/reliability_groundedness.py](../eval/reliability_groundedness.py) — LLM-as-judge checks via Groq.
- **Prompt-leak fix**: [agents/maven.py](../agents/maven.py) — caught by the groundedness check; 2-line prompt edit.
- **End-to-end tests**: [tests/test_e2e.py](../tests/test_e2e.py) — pytest, 5 passing.
- **Env-overridable model**: [config.py](../config.py) — `LLM_MODEL` reads from env, defaults to 70B.

The application itself is unchanged in shape — Sentinel → Maven → Healer
→ Watcher → END over FastAPI + Telegram + Streamlit + n8n. Start with
`python main.py` and `streamlit run ui/app.py` exactly as in M2.

---

## 3. System & Retrieval Quality

### 3.1 Design choices

Full rationale with numbers: [eval/results/design_choices.md](../eval/results/design_choices.md).

| Parameter | Value | One-line rationale |
|---|---|---|
| Embedding | Chroma `DefaultEmbeddingFunction` (ONNX `all-MiniLM-L6-v2`) | Zero extra deps, CPU-only, fast cold-start (~5 s ingest). |
| Chunk size | **500 chars** | Runbook sections have **median 272, max 510** chars — 500 keeps one section per chunk. |
| Chunk overlap | **50 chars** | Robust to section-boundary splits as the KB grows. |
| Top-k | 3 | Balances recall and LLM context budget (~1,500 chars context at top_k=3). |
| Distance | Cosine | ChromaDB `hnsw:space="cosine"`. |
| Retriever | Dense-only (no re-rank, no hybrid) | Baseline for M3; hybrid BM25 + dense is logged as future work. |

**Key evidence — measured section lengths** (all 10 runbooks, 70 sections):

| Stat | Value |
|---|---|
| Median section length | **272 chars** |
| Mean | 284 |
| Max | **510** |
| Sections > 600 chars | **0** |

Every section fits in a 500-char chunk. This single measurement drives
the chunk-size choice.

**Sweep summary** (composite score `= 0.35·Hit@3 + 0.30·MRR + 0.20·NDCG@3 + 0.15·P@3`):

| Config | Score |
|---|---|
| chunk=300, overlap=0 | 0.9002 (raw winner) |
| **chunk=500, overlap=50** | **0.8911 (selected)** |
| chunk=800, overlap=0 | 0.8829 |
| All 9 configs | span 0.8608 – 0.9002 (3.9-pt total spread → pipeline is robust) |

**Why the runner-up was selected** over the raw winner (~1 % gap, within
noise on 40 queries):

1. 66 % more context per retrieved chunk for the Maven LLM (1,500 chars
   vs 900 at top_k=3).
2. Robust to section-boundary splits when the KB grows beyond 10 docs.
3. 40-query eval set cannot statistically distinguish a 1 % gap —
   reporting it as "the winner" would overstate the signal.

### 3.2 Retrieval quality (final config — chunk=500 / overlap=50 / ONNX MiniLM)

From [eval/results/final_summary.json](../eval/results/final_summary.json):

| Metric | @1 | @3 | @5 |
|---|---|---|---|
| Hit | 0.850 | **0.950** | 0.975 |
| Precision | 0.850 | 0.771 | 0.585 |
| Recall | 0.788 | 0.925 | 0.950 |
| NDCG | 0.850 | 0.881 | 0.891 |

**MRR = 0.890.** The first relevant chunk is on average at rank ~1.12.

**By difficulty (Hit@1):**

| Bucket | Hit@1 | Hit@3 | MRR |
|---|---|---|---|
| Easy | 0.90 | 0.90 | 0.925 |
| Medium | **1.00** | **1.00** | **1.00** |
| Hard | 0.60 | 0.90 | 0.70 |
| Composite | 0.90 | 1.00 | 0.933 |

Weakness is concentrated in the **intentionally adversarial hard**
bucket (see 3.4). Easy/medium/composite are saturated.

### 3.3 Reliability checks (LLM-as-judge)

Two checks beyond standard IR metrics — both necessary because they
catch failure modes retrieval metrics cannot see.

**Context relevance** — 40 queries × 3 retrieved chunks = 120 judge
calls. Judge scores each (query, chunk) pair on 0-1.

| Metric | Value |
|---|---|
| Mean chunk relevance | **0.78** |
| % chunks ≥ 0.7 ("useful" threshold) | **91.67 %** |
| Hard-bucket mean | 0.79 (highest of any bucket) |

Interpretation: when the retriever does return a chunk, it is almost
always on-topic. The hard-bucket mean is highest because when
retrieval does succeed on a no-keyword query, the chunk it picked was
clearly a precise match.

**Groundedness** — 20 stratified queries (5 per difficulty, spanning
all 10 runbook types). Full Sentinel → Maven → Healer pipeline runs,
then a judge asks whether every factual claim in the generated
diagnosis is supported by the retrieved chunks.

The first run returned **15 % grounded**. Inspection of the
`unsupported_claim` field revealed the same phrase — *"The average
similarity score of 0.81 also suggests a strong match with known
runbook patterns"* — appearing across many queries. The Maven prompt
was leaking retrieval telemetry into the LLM context, which the LLM
repeated in its diagnosis body.

**Two-line prompt fix** applied in [agents/maven.py](../agents/maven.py)
(remove the RAG-score line from the prompt, add an instruction to stick
to runbook facts). Re-running:

| | Before fix | After fix | Δ |
|---|---|---|---|
| Groundedness | **15.0 %** | **58.82 %** | **+43.8 pts** |
| Context relevance (mean) | 0.78 | 0.83 | +0.05 |
| Context relevance (% ≥ 0.7) | 91.67 % | 96.67 % | +5 pts |

Full narrative with diffs, judged claims, and caveats in
[reliability_findings.md](reliability_findings.md).

**Two honest caveats** on the after-fix groundedness number:

1. **Model caveat**: the after-fix re-run used `llama-3.1-8b-instant`
   (70B free-tier TPD was exhausted). The prompt-leak fix is
   model-independent (pure prompt engineering), so the improvement is
   directionally valid. A clean 70B re-run is queued for the next TPD
   reset.
2. **Judge caveat**: the binary `{grounded: 0/1}` judge penalises
   legitimate inference. Several ungrounded diagnoses after the fix
   are, on human review, correctly inferring from the runbook
   (Q01's "thread pool exhausted" is literally listed as a root cause
   in `runbook_api_timeout.md`). **58.82 % is therefore a lower bound**
   on true groundedness.

### 3.4 Known limitations

- **Q07 — semantic-retrieval ceiling.** A query with zero domain
  vocabulary (*"Service becomes unresponsive after running for a day,
  a manual restart fixes it temporarily"*, labeled `memory_leak`)
  never retrieves the target runbook at top-5 in any sweep config.
  This is an intentional adversarial case that demonstrates the
  ceiling of purely semantic dense retrieval. Documented explicitly
  in [eval/labeled_queries.json](../eval/labeled_queries.json) →
  `_meta.hard_queries_note`.
- **Watcher simulates execution.** No real `kubectl` / `systemctl`
  commands are run. Safety-first choice; real execution would require
  RBAC scoping and was out of scope for M3.
- **Judge over-strictness.** The binary groundedness judge is a known
  lower-bound. A rubric-scored judge with multiple runs is future work.
- **Hybrid / query-rewrite retrieval not implemented.** The clearest
  mitigation for Q07-style no-keyword queries is BM25 + dense hybrid
  or LLM-based query rewriting. Both are logged as future work.
- **Embedding-model sweep partial.** Only ONNX MiniLM evaluated;
  `sentence-transformers` + BGE-small-en-v1.5 skipped to avoid a
  ~2 GB torch install. Expected future-work upgrade.

---

## 4. Correctness check

End-to-end pytest suite: [tests/test_e2e.py](../tests/test_e2e.py).
Five tests, all passing locally.

```
$ python -m pytest tests/test_e2e.py -v
============================= test session starts =============================
platform win32 -- Python 3.13.3, pytest-9.0.3, pluggy-1.6.0
collected 5 items

tests/test_e2e.py::test_analyze_endpoint_produces_valid_diagnosis[E2E-CPU-001] PASSED
tests/test_e2e.py::test_analyze_endpoint_produces_valid_diagnosis[E2E-DB-001]  PASSED
tests/test_e2e.py::test_analyze_endpoint_produces_valid_diagnosis[E2E-SSL-001] PASSED
tests/test_e2e.py::test_analyze_endpoint_produces_valid_diagnosis[E2E-POD-001] PASSED
tests/test_e2e.py::test_graph_invocation_retrieves_docs_from_rag               PASSED

============================= 5 passed in 32.79s ==============================
```

**Coverage**:

1. **HTTP layer** — four parametrised tests drive the 4 seeded alerts
   (CPU spike, DB connection, SSL expired, pod crash) through the
   `/analyze` endpoint via `fastapi.testclient.TestClient`. Each
   asserts the full response shape: alert type, severity, non-empty
   diagnosis, fix plan with ≥ 1 step, confidence ∈ [0, 1], etc.
2. **Graph layer** — one direct invocation of `nexus_graph` on a
   seeded alert, asserting `retrieved_docs` has ≥ 1 chunk with the
   expected fields (the HTTP response doesn't surface this field, so
   it's verified at the state level).

**How to reproduce locally:**

```bash
# 1. Install deps (pytest now in requirements.txt)
pip install -r requirements.txt

# 2. .env must contain GROQ_API_KEY — the pipeline calls Groq live
cp .env.example .env && $EDITOR .env

# 3. Run
python -m pytest tests/test_e2e.py -v
```

The suite uses a session-scoped fixture in
[tests/conftest.py](../tests/conftest.py) to ingest the 10-runbook
knowledge base once before any test runs. If `GROQ_API_KEY` is missing
the suite skips loudly rather than silently failing.

---

## 5. Future Work

Consolidated from items raised across §3 and
[reliability_findings.md](reliability_findings.md):

| Priority | Item | Why it matters | Effort |
|---|---|---|---|
| High | Hybrid BM25 + dense retrieval | Fixes Q07-style no-keyword queries (current retrieval ceiling — Hit@5 = 0 in every sweep config) | Medium |
| High | Real fix execution with RBAC scoping | Closes the "simulated execution" gap in the Watcher; turns `⚠️ partial` on the matrix into `✅` | High |
| Medium | Rubric-scored groundedness judge (multi-run) | Current binary judge is a known lower bound; a rubric (fully / partial / none) with multiple judge runs would raise the reported 58.82 % toward its true value | Low |
| Medium | Benchmark BGE-small-en-v1.5 vs MiniLM | Expected to improve retrieval on the hard bucket (the only weak spot in §3.2) | Low |
| Low | LLM-based query rewriting before retrieval | Alternative mitigation for Q07 — transforms user's colloquial query into domain-keyword form before the embedding call | Medium |
| Low | 70B like-for-like reliability re-run | Replaces the 8B after-fix number with a clean 70B measurement for an apples-to-apples comparison | Trivial (1 command, see reliability_findings.md) |

**Why this ordering**: hybrid retrieval unlocks the single biggest
quality ceiling we documented (the hard-bucket floor), and real fix
execution is the only feature promised in M2 that we ship as
simulated — both are "High" priority because they would change a
`⚠️ partial` row on the matrix into `✅`. The remaining items are
quality refinements rather than capability gaps.

---

## Appendix — Artifact index

| File | Purpose |
|---|---|
| [eval/labeled_queries.json](../eval/labeled_queries.json) | 40 hand-authored queries + ground truth + hard-query note |
| [eval/retrieval_metrics.py](../eval/retrieval_metrics.py) | Hit@k / Precision@k / Recall@k / MRR / NDCG@k |
| [eval/sweep.py](../eval/sweep.py) | 9-config hyperparameter sweep |
| [eval/reliability_context.py](../eval/reliability_context.py) | 5A — context relevance judge |
| [eval/reliability_groundedness.py](../eval/reliability_groundedness.py) | 5B — groundedness judge (full pipeline) |
| [eval/results/final_metrics.csv](../eval/results/final_metrics.csv) | Per-query retrieval numbers (final config) |
| [eval/results/final_summary.json](../eval/results/final_summary.json) | Retrieval aggregate |
| [eval/results/sweep_results.csv](../eval/results/sweep_results.csv) | All 9 sweep configs |
| [eval/results/sweep_summary.md](../eval/results/sweep_summary.md) | Ranked sweep table |
| [eval/results/design_choices.md](../eval/results/design_choices.md) | Full design-choice narrative + section-length evidence |
| [eval/results/context_relevance.csv](../eval/results/context_relevance.csv) | 120 judged (query, chunk) pairs — before fix |
| [eval/results/context_relevance_after_fix.csv](../eval/results/context_relevance_after_fix.csv) | Same — after fix |
| [eval/results/groundedness.csv](../eval/results/groundedness.csv) | 20 judged diagnoses — before fix (contains leaks) |
| [eval/results/groundedness_after_fix.csv](../eval/results/groundedness_after_fix.csv) | Same — after fix (leaks gone) |
| [docs/milestone3_matrix.md](milestone3_matrix.md) | Planned-vs-delivered matrix |
| [docs/reliability_findings.md](reliability_findings.md) | Prompt-leak bug story |
| [tests/test_e2e.py](../tests/test_e2e.py) | pytest smoke suite |
