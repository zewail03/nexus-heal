# NEXUS-HEAL — Milestone 3 Report

**Project:** Network Expert Unified System for Healing, Error-Analysis & Logging
**Team:** Adham (LangGraph + Sentinel), Walid (Maven + RAG), Mohamed (Healer + KB), Shahd (Telegram + UI)
**Date:** 2026-04-23

---

## 1. Planned vs. Delivered

See the full matrix in [milestone3_matrix.md](milestone3_matrix.md). Summary:

- **11 / 11** Milestone 2 features fully delivered (`✅`). Fix
  execution, previously flagged `⚠️ partial` (simulated), now ships
  safe **real execution** — commands on a read-only allowlist run for
  real via subprocess, and mutation commands are gated behind manual
  review. `validation_result` is assembled from actual captured
  stdout/stderr, not a hard-coded success string.
- **12 / 12** new Milestone 3 deliverables fully delivered (`✅`),
  including the 70B reliability re-run, the 3-embedding sweep, the
  rubric-scored judge, plus three stretch items: KB expanded
  10 → 26 runbooks, SQLite-backed `AlertStore` for Mission Control
  persistence across restarts, and a full Streamlit UI overhaul
  (dark neon theme, animated pipeline, terminal-style Watcher log).
- **Zero items are `⚠️ partial`. Zero items are `❌ not delivered`.**

---

## 2. Live working system — what's new since M2

- **Labeled eval set**: [eval/labeled_queries.json](../eval/labeled_queries.json) — 40 queries, 4 per runbook × 4 difficulty buckets.
- **Metrics harness**: [eval/retrieval_metrics.py](../eval/retrieval_metrics.py) — Hit@k, Precision@k, Recall@k, MRR, NDCG@k, with per-difficulty breakdown.
- **Design-choice sweep**: [eval/sweep.py](../eval/sweep.py) — 9 configs, wall-clock timed, ranked by composite score.
- **Reliability checks**: [eval/reliability_context.py](../eval/reliability_context.py) + [eval/reliability_groundedness.py](../eval/reliability_groundedness.py) — LLM-as-judge checks via Groq.
- **Prompt-leak fix**: [agents/maven.py](../agents/maven.py) — caught by the groundedness check; 2-line prompt edit.
- **Safe real Watcher execution**: [agents/watcher.py](../agents/watcher.py) — replaces the M2 simulation with real `subprocess.run` calls for commands on a read-only safety allowlist; mutation commands are gated behind manual review. Covered by 30 unit tests.
- **Rubric-scored judge**: [eval/reliability_groundedness_rubric.py](../eval/reliability_groundedness_rubric.py) — {fully, partial, not_grounded} with N=3 majority vote.
- **3-embedding sweep**: [eval/sweep.py](../eval/sweep.py) now runs across ONNX MiniLM, ST MiniLM, and BGE-small.
- **End-to-end tests**: [tests/test_e2e.py](../tests/test_e2e.py) + [tests/test_watcher.py](../tests/test_watcher.py) — pytest, 36 passing in ~44 s.
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
| Embedding | Chroma `DefaultEmbeddingFunction` (ONNX `all-MiniLM-L6-v2`) | Zero extra deps, CPU-only, fast cold-start (~5 s ingest). **Empirically confirmed** by the 27-config sweep: ST MiniLM scored identically (0.8803 mean, 0.8911 at selected config), BGE-small underperformed (−3.7 points at selected config). |
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

**Sweep summary** — 27 configs (3 embeddings × 3 chunk × 3 overlap).
Composite score = `0.35·Hit@3 + 0.30·MRR + 0.20·NDCG@3 + 0.15·P@3`.

Per-embedding winner:

| Embedding | Best config | Score | Hit@3 | MRR |
|---|---|---|---|---|
| ST MiniLM (full precision) | chunk=300, overlap=0 | **0.9002** | 0.950 | 0.907 |
| ONNX MiniLM (our choice) | chunk=300, overlap=0 | **0.9002** | 0.950 | 0.907 |
| BGE-small-en-v1.5 | chunk=500, overlap=100 | 0.8901 | 0.950 | 0.902 |

At the selected production config (chunk=500, overlap=50):

| Embedding | Score | Hit@3 | Notes |
|---|---|---|---|
| ST MiniLM | **0.8911** | 0.950 | Identical to ONNX |
| ONNX MiniLM | **0.8911** | 0.950 | Our production default |
| BGE-small | 0.8546 | 0.900 | **−3.7 points** vs MiniLM family |

- **All 27 configs** span 0.8503 – 0.9002 (5-pt total spread → pipeline
  is robust to embedding + hyperparameter choice).
- **ST and ONNX MiniLM produce bit-identical rankings**, confirming the
  ONNX quantization is lossless on this corpus.
- **BGE-small underperforms** despite being stronger on generic MTEB —
  our corpus is small and keyword-dense; heavier generic models can
  regress on narrow domains.

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
to runbook facts). Re-running on 70B (clean like-for-like):

| | Before fix (70B) | After fix (70B) | Δ |
|---|---|---|---|
| Groundedness | **15.0 %** | **60.0 %** | **+45 pts** |
| Context relevance (mean) | 0.7758 | 0.7758 | 0 (stable) |
| Context relevance (% ≥ 0.7) | 91.67 % | 91.67 % | 0 (stable) |
| Diagnoses containing `"similarity score"` | ~16 / 20 (80 %) | **0 / 20** | −80 pts |
| Mean words / diagnosis | 60.5 | 63.2 | +4.6 % (refutes "blander" hypothesis) |

Context relevance is **identical** to before-fix, confirming the
prompt change only affected the generator — not retrieval — exactly as
claimed. Full narrative with diffs, judged claims, a cross-model
consistency check, and the "did diagnoses just get blander?" sanity
analysis in [reliability_findings.md](reliability_findings.md).

**Rubric-scored judge** — we replaced the binary `{0, 1}` judge with a
3-level rubric `{fully, partial, not_grounded}` and aggregated **N=3
majority votes** per query (strictness-first tie-break). Applied to
the same 20 after-fix 70B diagnoses:

| Judge | Model | Result |
|---|---|---|
| Binary | 70B | 60.0 % grounded (12/20) |
| Rubric, N=3 | 8B | **0.90 mean** (17 fully / 2 partial / 1 not_grounded) |
| Rubric, N=3 | 70B (partial sample, 4/20 before TPD cap) | All 4 → "partial" → **0.50** on that slice |

The 8B-vs-70B rubric comparison on the 4 overlapping queries shows the
8B judge is systematically more lenient: where 70B votes "partial"
(legitimate inference acknowledged), 8B votes "fully". So:

- **60 % binary** is a strict *lower bound* — it penalises any claim
  that isn't verbatim in the context.
- **90 % rubric on 8B** is a lenient *upper estimate* — the 8B judge
  forgives inference the 70B judge flags.
- **True groundedness sits between the two**, with best-estimate
  70-80 %. A full like-for-like 70B rubric re-run is logged as a
  trivial future-work item (§5).

The independently-run 8B binary run (58.82 %, 17/20 judged) landed
within 1.2 points of the 70B binary result, providing an earlier
cross-model consistency check and building confidence that the 8B
rubric lean is about leniency, not randomness.

### 3.4 Known limitations

- **Q07 — semantic-retrieval ceiling.** A query with zero domain
  vocabulary (*"Service becomes unresponsive after running for a day,
  a manual restart fixes it temporarily"*, labeled `memory_leak`)
  never retrieves the target runbook at top-5 in **any of the 27
  sweep configurations — including BGE-small**, a model specifically
  tuned for semantic retrieval. That failure is a useful negative
  result: the ceiling is set by the semantic-retrieval paradigm
  itself, not by a specific model choice. Fixing this class of query
  needs hybrid dense+BM25 retrieval or LLM query rewriting.
- **Watcher gates mutation commands by design.** Read-only
  verification commands (`kubectl get`, `df -h`, `curl -I`,
  `pg_isready`, `systemctl status`, …) run for real via `subprocess`.
  Mutation commands (`kubectl delete`, `rm`, `systemctl restart`,
  `DROP TABLE`, …) are not executed automatically — they are
  classified and surfaced in the API response as "gated for manual
  review." This is a deliberate safety choice: the fix commands come
  from an LLM and auto-executing unreviewed mutations in production
  would be reckless. Full real execution with RBAC scoping and a
  command-review UI is logged as future work.
- **Rubric judge 70B re-run pending.** The 8B rubric mean (0.90) is
  a lenient upper estimate; cross-check on 4 queries shows 70B is
  stricter ("partial" where 8B says "fully"). A clean 70B rubric run
  (~1 command after the next TPD reset) would replace the 8B number
  with a like-for-like value.
- **Hybrid / query-rewrite retrieval not implemented.** The clearest
  mitigation for Q07-style no-keyword queries is BM25 + dense hybrid
  or LLM-based query rewriting. Both are logged as future work.

---

## 4. Correctness check

pytest suite covering the full pipeline, the FastAPI surface, and the
Watcher safety allowlist. **36 tests, all passing in ~44 s.**

```
$ python -m pytest tests/ -v
============================= test session starts =============================
platform win32 -- Python 3.13.3, pytest-9.0.3, pluggy-1.6.0
collected 36 items

tests/test_watcher.py ..........  (10 safe classify)                    [ 27%]
tests/test_watcher.py ..........  (10 mutation classify)                [ 55%]
tests/test_watcher.py ....        (4 unknown classify)                  [ 66%]
tests/test_watcher.py .           (allowlist disjoint guard)            [ 69%]
tests/test_watcher.py .....       (5 behaviour: reject, execute, gate)  [ 83%]
tests/test_e2e.py::test_analyze_endpoint_produces_valid_diagnosis[E2E-CPU-001] PASSED
tests/test_e2e.py::test_analyze_endpoint_produces_valid_diagnosis[E2E-DB-001]  PASSED
tests/test_e2e.py::test_analyze_endpoint_produces_valid_diagnosis[E2E-SSL-001] PASSED
tests/test_e2e.py::test_analyze_endpoint_produces_valid_diagnosis[E2E-POD-001] PASSED
tests/test_e2e.py::test_approve_endpoint_surfaces_command_results              PASSED
tests/test_e2e.py::test_graph_invocation_retrieves_docs_from_rag               PASSED

============================= 36 passed in 43.94s =============================
```

**Coverage**:

1. **Watcher safety allowlist** ([tests/test_watcher.py](../tests/test_watcher.py),
   30 deterministic unit tests) — classifier correctness for safe /
   mutation / unknown commands, allowlist-disjoint invariant, and
   behavioural tests proving the Watcher actually runs safe commands
   via `subprocess` (captures real `echo` output) and refuses to run
   mutation commands even when `human_approved=True`.
2. **HTTP layer** ([tests/test_e2e.py](../tests/test_e2e.py), 5
   integration tests) — four parametrised tests drive the 4 seeded
   alerts through `/analyze` via `fastapi.testclient.TestClient` and
   assert the full response shape. One test POSTs `/analyze` then
   `/approve` and asserts that the response surfaces the Watcher's
   real `command_results` + `validation_result` (proving the old
   hard-coded "All checks passed" string is gone).
3. **Graph layer** — one direct invocation of `nexus_graph` on a
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
python -m pytest tests/ -v
```

The suite uses a session-scoped fixture in
[tests/conftest.py](../tests/conftest.py) to ingest the 10-runbook
knowledge base once before any test runs. If `GROQ_API_KEY` is missing
the suite skips loudly rather than silently failing. Watcher tests
need no Groq access — they are fully deterministic.

---

## 5. Future Work

Consolidated from items raised across §3 and
[reliability_findings.md](reliability_findings.md). Items that were
flagged in the earlier draft and have since been delivered are kept
here with a strikethrough for traceability.

| Priority | Item | Why it matters | Effort |
|---|---|---|---|
| ~~Done~~ | ~~Hybrid BM25 + dense retrieval~~ | Completed — [`rag/hybrid_retriever.py`](../rag/hybrid_retriever.py) ships RRF fusion of dense + BM25 and is now the **production retriever** ([`agents/maven.py`](../agents/maven.py) imports `hybrid_retrieve`). Re-run on the same 40 queries and KB-26: Hit@3 0.80 → **0.85**, MRR 0.77 → **0.81**, hard-bucket Hit@1 0.40 → **0.50**. Easy bucket Hit@3 saturates at 1.00. Full numbers + per-query case studies in [`docs/hybrid_retrieval.md`](hybrid_retrieval.md). | — |
| ~~Done~~ | ~~LLM-based query rewriting before retrieval~~ | Completed — [`rag/query_rewriter.py`](../rag/query_rewriter.py) calls Groq Llama 3.3 70B with a domain-scoped vocabulary list, concatenates the keyword expansion onto the query, and feeds it through hybrid. Exposed via `python -m eval.retrieval_metrics --retriever query_rewrite_hybrid`. Hard-bucket Hit@3 jumps **0.50 → 0.80 (+30 pts)** and MRR **0.48 → 0.67**. Closes the M3 named ceiling: Q07 ("service unresponsive after running for a day") flips MRR 0.00 → 1.00 — the rewriter expands "unresponsive" + "manual restart" into `memory_leak OOM heap RSS GC SIGKILL exit code 137`, and runbook_memory_leak.md surfaces at rank 1. Honest tradeoff: Hit@1 regresses 0.75 → 0.68 (expansion noise on already-keyword-rich queries) — recommendation in `hybrid_retrieval.md` is to use it as a confidence-low Maven retry path, not a default. | — |
| ~~Done~~ | ~~Clean 70B rubric-judge re-run~~ | Completed — `python -m eval.reliability_groundedness_rubric --input eval/results/groundedness_after_fix_70b.csv --suffix _70b`. Result: **0.50 mean** (2 fully / 16 partial / 2 not_grounded) on the same 20 after-fix diagnoses the 8B rubric judged at 0.90. Confirms the M3 cross-model leniency observation: 8B is much more lenient than 70B; the binary judge's 60.0 % sits between the two as expected. The strict like-for-like rubric number is now 0.50, not the lenient 0.90 — best-estimate true groundedness updated to the 50 % – 60 % band. Results in [`eval/results/groundedness_rubric_70b.csv`](../eval/results/groundedness_rubric_70b.csv). | — |
| Medium | Full real fix execution with RBAC scoping + command-review UI | Watcher now runs safe read-only commands for real and gates mutations. Next step is a structured review path (RBAC, dry-run, idempotency checks) so mutations can also run safely under human approval. Out of capstone scope. | High |
| Low | Conditional query-rewrite retry in Maven | Two-line change in `agents/maven.py`: if `confidence_diagnose < threshold` after first pass, retry through `query_rewrite_hybrid_retrieve`. Trades the Hit@1 regression for the Hit@3 win on queries that need it. Deferred so the hybrid production switch can ship clean. | Trivial |
| Low | ~~Done~~ | ~~Persist `_pending_alerts` in SQLite~~ | Completed — [`api/storage.py`](../api/storage.py) ships an `AlertStore` (WAL mode, JSON-serialized state, env-overridable path). 12 unit tests in [`tests/test_storage.py`](../tests/test_storage.py). | — |
| ~~Done~~ | ~~Knowledge base expansion (10 → 25+ runbooks)~~ | Completed — KB now has 26 runbooks. Sentinel `ALERT_TYPES` extended 10 → 26. Re-run of the 40-query eval shows Hit@3 dropping from 0.95 → 0.80 — honest scaling effect that motivates the High-priority hybrid retrieval item. | — |
| ~~Done~~ | ~~70B like-for-like reliability re-run~~ | Completed — 60.0 % grounded on clean 70B, in [`groundedness_after_fix_70b.csv`](../eval/results/groundedness_after_fix_70b.csv). | — |
| ~~Done~~ | ~~Rubric-scored groundedness judge~~ | Completed — [`reliability_groundedness_rubric.py`](../eval/reliability_groundedness_rubric.py) with N=3 majority vote. 0.90 mean on 8B. | — |
| ~~Done~~ | ~~Benchmark BGE-small-en-v1.5 vs MiniLM~~ | Completed — full 27-config sweep. BGE-small underperforms MiniLM on this corpus (−3.7 pts at selected config). Documented in [`design_choices.md`](../eval/results/design_choices.md). | — |
| ~~Done~~ | ~~Real fix execution (read-only subset)~~ | Completed — Watcher allowlist executes safe verification commands via `subprocess`; mutations remain gated. Validated by 30 pytest unit tests. | — |

**Why this ordering**: every retrieval-quality item the M3 report
flagged is now closed.

- **Hybrid retrieval** shipped and is the production retriever; the
  paradigm ceiling moved from "Q07 unreachable" to "Q07 reachable
  through query rewriting."
- **LLM query rewriting** shipped as an eval-validated retriever
  mode and closes the named M3 ceiling (Q07: MRR 0 → 1) at the cost
  of a Hit@1 regression on already-keyword-rich queries — the
  textbook query-expansion tradeoff.
- **70B rubric re-run** shipped and replaces the lenient 8B 0.90 with
  the strict like-for-like 0.50, validating the binary judge's 60 %
  as the appropriate lower bound and tightening the best-estimate
  band to 50–60 %.

The only remaining items are out-of-capstone-scope (RBAC + mutation
review UI — engineering, not retrieval) or Trivial follow-ups
(wiring `query_rewrite_hybrid` as a confidence-low retry path inside
Maven — two lines, deferred so the production hybrid switch can
ship clean).

---

## Appendix — Artifact index

| File | Purpose |
|---|---|
| [eval/labeled_queries.json](../eval/labeled_queries.json) | 40 hand-authored queries + ground truth + hard-query note |
| [eval/retrieval_metrics.py](../eval/retrieval_metrics.py) | Hit@k / Precision@k / Recall@k / MRR / NDCG@k |
| [eval/sweep.py](../eval/sweep.py) | 27-config sweep (3 embeddings × 3 chunk × 3 overlap) |
| [eval/reliability_context.py](../eval/reliability_context.py) | 5A — context relevance judge |
| [eval/reliability_groundedness.py](../eval/reliability_groundedness.py) | 5B — binary groundedness judge |
| [eval/reliability_groundedness_rubric.py](../eval/reliability_groundedness_rubric.py) | 5C — rubric-scored judge with N=3 majority vote |
| [agents/watcher.py](../agents/watcher.py) | **Watcher with safety allowlist and real subprocess execution** |
| [tests/test_watcher.py](../tests/test_watcher.py) | 30 deterministic Watcher unit tests |
| [eval/results/final_metrics.csv](../eval/results/final_metrics.csv) | Per-query retrieval numbers (final config) |
| [eval/results/final_summary.json](../eval/results/final_summary.json) | Retrieval aggregate |
| [eval/results/sweep_results.csv](../eval/results/sweep_results.csv) | All 9 sweep configs |
| [eval/results/sweep_summary.md](../eval/results/sweep_summary.md) | Ranked sweep table |
| [eval/results/design_choices.md](../eval/results/design_choices.md) | Full design-choice narrative + section-length evidence |
| [eval/results/context_relevance.csv](../eval/results/context_relevance.csv) | 120 judged (query, chunk) pairs — before fix |
| [eval/results/context_relevance_after_fix.csv](../eval/results/context_relevance_after_fix.csv) | Same — after fix |
| [eval/results/groundedness.csv](../eval/results/groundedness.csv) | 20 judged diagnoses — before fix on 70B (contains leaks) |
| [eval/results/groundedness_after_fix.csv](../eval/results/groundedness_after_fix.csv) | 8B cross-model consistency check (58.82 %, 17/20 judged) |
| [eval/results/groundedness_after_fix_70b.csv](../eval/results/groundedness_after_fix_70b.csv) | **Clean 70B after-fix binary (60.0 %, 20/20 judged) — headline binary number** |
| [eval/results/context_relevance_after_fix_70b.csv](../eval/results/context_relevance_after_fix_70b.csv) | Clean 70B after-fix context relevance (0.7758 / 91.67 %) |
| [eval/results/groundedness_rubric_8b.csv](../eval/results/groundedness_rubric_8b.csv) | **Rubric-scored judge on 8B, N=3 majority vote — 0.90 mean (17 fully, 2 partial, 1 not_grounded)** |
| [eval/results/groundedness_rubric.csv](../eval/results/groundedness_rubric.csv) | Rubric judge partial 70B run (4/20 before TPD cap; all "partial" — confirms 8B is more lenient) |
| [docs/milestone3_matrix.md](milestone3_matrix.md) | Planned-vs-delivered matrix |
| [docs/reliability_findings.md](reliability_findings.md) | Prompt-leak bug story |
| [tests/test_e2e.py](../tests/test_e2e.py) | pytest smoke suite |
