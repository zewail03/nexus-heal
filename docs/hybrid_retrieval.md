# Hybrid BM25 + Dense Retrieval — Final Milestone

**Status:** ✅ Delivered
**Date:** 2026-05-10
**Owner:** Adham
**Code:** [rag/hybrid_retriever.py](../rag/hybrid_retriever.py) · [eval/retrieval_metrics.py](../eval/retrieval_metrics.py)
**Results:** [eval/results/kb26_dense_*](../eval/results/) (baseline) · [eval/results/kb26_hybrid_*](../eval/results/) (after)

---

## TL;DR

The Milestone 3 report flagged hybrid BM25 + dense retrieval as the
single remaining **High-priority** Future-Work item — the only proposal
that targeted the Q07/hard-bucket ceiling. It now ships, evaluated on
the same 40 labeled queries used for the M3 retrieval headline, against
the post-stretch KB-26.

| Metric (overall) | Dense (KB-26) | Hybrid RRF | Δ |
|---|---|---|---|
| Hit@1 | 0.7250 | **0.7500** | **+2.5 pts** |
| Hit@3 | 0.8000 | **0.8500** | **+5.0 pts** |
| Hit@5 | 0.8750 | **0.9000** | +2.5 pts |
| Precision@3 | 0.5667 | **0.6167** | +5.0 pts |
| Recall@3 | 0.7750 | **0.8250** | +5.0 pts |
| NDCG@3 | 0.7464 | **0.7905** | +4.4 pts |
| **MRR** | 0.7717 | **0.8058** | **+3.4 pts** |

The biggest gain is exactly where the M3 report said the ceiling was:

| Hard bucket | Dense | Hybrid | Δ |
|---|---|---|---|
| Hit@1 | 0.400 | **0.500** | **+10.0 pts** |
| MRR | 0.4783 | **0.5200** | +4.2 pts |

Hybrid breaks through on hard queries that share at least one technical
keyword with their target runbook (Q31's MRR jumps from 0.33 to **1.00**),
without regressing easy or medium buckets — easy Hit@3 actually saturates
at **1.00**.

---

## Why this — the M3 ceiling, revisited

The 27-config sweep in [eval/results/design_choices.md](../eval/results/design_choices.md) showed every dense
configuration — including BGE-small, a model specifically tuned for
semantic retrieval — fails on **Q07**:

> *"Service becomes unresponsive after running for a day, a manual
> restart fixes it temporarily"* (labeled `memory_leak`)

That failure is paradigm-level, not embedding-level. The query has
**zero shared vocabulary** with the target runbook (which uses "OOM",
"leak", "heap", "RSS", …). No dense embedding can bridge that —
embeddings are built on co-occurrence statistics that need *some*
shared signal to anchor on.

Hybrid retrieval is the textbook answer. BM25 anchors on shared
lexical units (rare words, technical terms, error codes); dense
embeddings catch paraphrases. Either signal alone misses queries the
other catches; their union is strictly more expressive.

---

## Implementation — Reciprocal Rank Fusion

[rag/hybrid_retriever.py](../rag/hybrid_retriever.py) implements RRF
(Cormack et al., 2009) over the existing ChromaDB collection plus a
BM25Okapi index built lazily on first call:

```
score_RRF(d) = Σ over rankers r of  1 / (k + rank_r(d))      (k = 60)
```

**Why RRF over a weighted score sum.** BM25 and cosine live in
different score scales — BM25 has an open upper range that depends on
corpus statistics; cosine sits in [0, 1]. Min-max normalising before
fusion would silently couple to corpus changes (the "max" shifts every
time the KB grows). RRF fuses by *rank*, so the two legs cannot drown
each other out and the constant `k = 60` is a published default that
generalises across IR benchmarks.

**Drop-in shape.** `hybrid_retrieve(...)` returns the same dict shape
as [retrieve_docs](../rag/retriever.py) plus an extra `fusion_score`
field. Existing code paths reading `score`, `content`, `source`,
`alert_type` continue to work unchanged.

**BM25-only hits.** When BM25 surfaces a chunk dense did not retrieve,
its `score` field is filled with **0.0** rather than a fabricated
cosine value. Maven's confidence calibration math reads `score`, so
this keeps the confidence honest about lexical-only matches.

**Empty-query handling.** If a query produces zero non-stopword tokens
that appear anywhere in the corpus, the BM25 leg is skipped entirely —
otherwise RRF would inject a uniform rank for every doc and dilute the
dense signal.

---

## Results — full breakdown

Both runs use the same 40 labeled queries and the same KB-26 ChromaDB
collection (chunk = 500, overlap = 50, ONNX MiniLM). Top-k = 5.

### Aggregate

| Metric | @1 (dense) | @1 (hybrid) | @3 (dense) | @3 (hybrid) | @5 (dense) | @5 (hybrid) |
|---|---|---|---|---|---|---|
| Hit | 0.725 | **0.750** | 0.800 | **0.850** | 0.875 | **0.900** |
| Precision | 0.725 | **0.750** | 0.567 | **0.617** | 0.435 | **0.480** |
| Recall | 0.675 | **0.700** | 0.775 | **0.825** | 0.850 | **0.863** |
| NDCG | 0.725 | **0.750** | 0.746 | **0.791** | 0.778 | **0.806** |

**MRR:** 0.7717 (dense) → **0.8058 (hybrid)** · **+3.4 pts**

### By difficulty

| Bucket | Hit@1 (D / H) | Hit@3 (D / H) | Hit@5 (D / H) | MRR (D / H) |
|---|---|---|---|---|
| Easy | 0.80 / 0.80 | 0.90 / **1.00** | 0.90 / **1.00** | 0.85 / **0.88** |
| Medium | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 |
| Hard | 0.40 / **0.50** | 0.50 / 0.50 | 0.70 / 0.60 ⚠️ | 0.48 / **0.52** |
| Composite | 0.70 / 0.70 | 0.80 / **0.90** | 0.90 / **1.00** | 0.76 / **0.82** |

Composite (multi-target) and easy queries see the cleanest wins —
both saturate at Hit@5 = 1.00. Medium was already saturated at 1.00
across the board; nothing to improve.

The hard bucket needs unpacking — it has the biggest @1 win and the
only metric regression in the whole report.

### Hard-bucket case studies

The CSV diff shows three flips on hard queries:

| QID | Query | Dense | Hybrid | Outcome |
|---|---|---|---|---|
| **Q31** | "New deployment will not stabilize, readiness probe failing after rollout" | `pod_crash` at rank 3 | `pod_crash` at rank **1** | **MRR 0.33 → 1.00** |
| Q15 | "Pods get killed every few hours, no obvious memory pressure" | `pod_crash` at rank 4 | `pod_crash` at rank 5 | MRR 0.25 → 0.20 (within-rank shuffle) |
| Q03 | "Application feels slow today, users complaining but nothing obvious in logs" | `cpu_spike` at rank 5 | not in top-5 | MRR 0.20 → 0.00 (regression) |

**Q31 is the win this milestone targeted.** The query carries
"readiness probe", "rollout", "deployment" — domain keywords that
appear verbatim in `runbook_pod_crash.md`. Dense ranked the right
runbook at 3 (semantically similar but ambiguous with WebSocket/secrets
content); BM25 immediately pinned it at 1; RRF combined the agreement
into a clean rank-1 retrieval.

**Q03 is the honest cost.** The query is fully paraphrased — *"feels
slow"*, *"users complaining"*, *"nothing obvious"* — none of which
appear in the cpu_spike runbook. Dense barely caught it at rank 5
through weak embedding overlap; BM25 saw no signal at all and surfaced
lexically-similar but semantically-wrong runbooks
(`api_timeout`, `disk_full`, `cdn_cache_miss`), which displaced the
fragile dense rank-5 hit. **The hybrid Hit@5 regression is concentrated
on this single query.**

**Q07 — paradigm ceiling holds.** The Milestone 3 report's named
worst-case (*"Service becomes unresponsive after running for a day, a
manual restart fixes it temporarily"*) still misses in hybrid. BM25
can't help where the lexical signal is empty, dense can't help where
there's no embedding overlap. Q07 marks the boundary of what
retrieval-only methods can do — fixing it requires LLM-based query
rewriting, listed as Low-priority Future Work in the M3 report.

---

## Reproducibility

```bash
pip install -r requirements.txt   # rank_bm25 now in the production install

# Dense baseline (the M3 KB-26 number)
python -m eval.retrieval_metrics --retriever dense  --name kb26_dense

# Hybrid (this milestone)
python -m eval.retrieval_metrics --retriever hybrid --name kb26_hybrid
```

Both writes land under [eval/results/](../eval/results/) and are
checked in. No randomness — RRF and BM25 are deterministic, the
ChromaDB nearest-neighbour query is deterministic; runs are
bit-reproducible.

---

## Production switch

Maven now imports `hybrid_retrieve` directly ([agents/maven.py](../agents/maven.py)).
The hybrid retriever pulls the full dense ranking once per query
(cheap for our 80-chunk corpus) so every returned chunk — including
BM25-only hits — carries a real cosine score. Maven's confidence
calibration math (`40 % LLM × 35 % avg-RAG × 25 % alert-specificity`)
stays honest about lexical-only matches without needing changes of
its own. All 48 pytest tests (42 deterministic + 6 e2e) pass against
the hybrid retriever.

## Going further — LLM query rewriting

Q07 and Q03 still miss in plain hybrid. Both have *zero* domain
vocabulary — the dense leg is paraphrase-tolerant only up to a point,
and BM25 has nothing to anchor on when the words don't match. The
textbook fix beyond hybrid is to rewrite the query into keyword form
*before* retrieval, surfacing the technical terms that runbooks
actually contain.

[rag/query_rewriter.py](../rag/query_rewriter.py) calls Groq Llama 3.3
70B with a domain-scoped vocabulary list and concatenates the LLM's
keyword expansion onto the original query. Both legs of hybrid then
run on the augmented query. In-process cached so repeated calls cost
zero tokens.

**Example — Q07** (the M3 named ceiling):

```
Input  : "Service becomes unresponsive after running for a day, a manual
          restart fixes it temporarily"
Expand : "... memory_leak cpu_spike OOM OOMKilled heap RSS swap GC JVM
          CrashLoopBackOff exit code 137 SIGKILL kubectl"
Top-3  : runbook_memory_leak.md, runbook_memory_leak.md, runbook_pod_crash.md
MRR    : 0.00 → 1.00
```

### Three-way comparison

| Metric (overall) | Dense | Hybrid | **+ Query Rewrite** |
|---|---|---|---|
| Hit@1 | 0.725 | **0.750** | 0.675 ⚠️ |
| Hit@3 | 0.800 | 0.850 | **0.900** |
| Hit@5 | 0.875 | 0.900 | **0.925** |
| MRR | 0.7717 | **0.8058** | 0.7842 |

| Hard bucket | Dense | Hybrid | **+ Query Rewrite** |
|---|---|---|---|
| Hit@1 | 0.400 | 0.500 | **0.600** |
| Hit@3 | 0.500 | 0.500 | **0.800** |
| Hit@5 | 0.700 | 0.600 | **0.800** |
| MRR | 0.4783 | 0.5200 | **0.6667** |

Query rewriting is **the textbook hard-bucket fix**: Hit@3 jumps from
0.50 → **0.80** (+30 pts) and MRR from 0.48 → **0.67**. The two named
M3 ceiling queries (Q07, Q15) and one previously-unsolved adversarial
query (Q23) all flip to Hit@3 = 1.

The honest tradeoff is real:

- **Hit@1 regresses** (0.75 → 0.68) — when the original query was
  *already* keyword-rich, expansion adds noise that displaces a
  rank-1 hit. Net per-query at Hit@3: +3 wins (all hard) vs −1 loss
  (one medium query, Q26).
- **One Groq call per unique query** (cached). Adds ~0.3 s p50
  latency to the first retrieval for a query. Acceptable for an SRE
  agent, undesirable for a search-as-you-type product.

### Recommendation

| Mode | When to use | Where |
|---|---|---|
| `dense` | Reproducing M3 baseline numbers | Eval only |
| `hybrid` | **Production default** | [agents/maven.py](../agents/maven.py) |
| `query_rewrite_hybrid` | Confidence-low retry path; eval Q07-class ceilings | Eval today; conditional production retry path is logged as Future Work |

The natural next step is to make query rewriting a **conditional retry
strategy**: run plain hybrid first, then if Maven's
`confidence_diagnose < threshold`, retry once through
`query_rewrite_hybrid`. This trades the Hit@1 regression for the
Hit@3 win on the queries that actually needed it. It's a two-line
change in [agents/maven.py](../agents/maven.py); deferred so the
production switch can ship clean.

## What's *not* changed

- **Knowledge base unchanged.** Still 26 runbooks; no new content was
  added for this milestone. The wins are purely retrieval-side.
- **No prompt changes to Maven/Healer/Watcher.** All three agent
  prompts are byte-for-byte identical to the M3 release.

---

## Takeaways

1. **The M3 ceiling was real, and hybrid moved it.** Hard-bucket
   Hit@1 = 0.40 → 0.50; overall Hit@3 = 0.80 → 0.85; MRR = 0.77 → 0.81.
   The single hardest query named in the M3 report (Q07) still misses,
   confirming the *paradigm-level* ceiling identified in
   `design_choices.md` — even hybrid retrieval cannot help when the
   query has zero domain vocabulary.
2. **Honest regression: Q03 fell out of top-5.** A fragile rank-5
   dense hit was displaced by BM25 noise. This is the textbook hybrid
   failure mode and motivates LLM-based query rewriting (M3 Future Work,
   Low priority) as the next step beyond hybrid.
3. **No infrastructure cost.** `rank_bm25` is pure Python, ~9 KB
   wheel, no native deps. Cold-start build of the BM25 index over 26
   runbooks completes in < 50 ms; thereafter cached.
