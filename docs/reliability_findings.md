# Reliability Findings — Prompt-Leak Bug Caught by LLM-as-Judge

## What we found

Running the LLM-as-judge **groundedness** check on 20 stratified queries
(5 per difficulty) against the full Sentinel → Maven → Healer pipeline,
only **15 % (3/20)** of diagnoses were judged fully grounded in the
retrieved runbook chunks. Breakdown before fix:

| Difficulty | Grounded % |
|---|---|
| Easy | 20 % |
| Medium | 20 % |
| Hard | **0 %** |
| Composite | 20 % |
| **Overall** | **15 %** |

Inspecting the `unsupported_claim` field the judge returned, the same
phrase appeared across queries from different runbooks:

> *"The average similarity score of 0.81 also suggests a strong match with known runbook patterns."*
>
> *"The average similarity score of 0.81 suggests a strong match with known runbook patterns."*
>
> *"The average similarity score of 0.73 suggests a moderate match…"*

Those scores are **not** in any runbook. They are numbers the LLM was
seeing in its own prompt and repeating back in the diagnosis body.

## Root cause

The Maven prompt was passing retrieval telemetry into the LLM context as
a "calibration hint":

```python
# agents/maven.py — before fix
prompt = f"""...
ALERT: {state['alert_raw']}
TYPE: {state['alert_type']}
SEVERITY: {state['alert_severity']}
RAG RETRIEVAL QUALITY: average similarity score = {avg_rag_score:.2f} (1.0 = perfect match, 0.5 = weak match)

RELEVANT RUNBOOKS:
{context}
...
"""
```

`avg_rag_score` was intended only to help the LLM calibrate its
confidence score. In practice the LLM lifted the number verbatim into
the free-text `diagnosis` field, turning an internal telemetry value
into a user-facing factual-sounding claim. Because the score is not
supported anywhere in the retrieved chunks, the groundedness judge
correctly flagged every such diagnosis as ungrounded.

`avg_rag_score` is still used, and *should* still be used, for the
downstream confidence-blending math
(`0.40·llm_confidence + 0.35·rag_factor + 0.25·specificity_factor`).
That is internal state; it has no business being in the prompt.

## Fix

Two lines removed, one added — in [agents/maven.py](../agents/maven.py):

```diff
 ALERT: {state['alert_raw']}
 TYPE: {state['alert_type']}
 SEVERITY: {state['alert_severity']}
-RAG RETRIEVAL QUALITY: average similarity score = {avg_rag_score:.2f} (1.0 = perfect match, 0.5 = weak match)
-
-RELEVANT RUNBOOKS:
+
+RELEVANT RUNBOOKS:
 {context}
+
+Base your diagnosis ONLY on the alert and the runbooks above. Do not mention
+similarity scores, retrieval quality, or any metadata — only facts from the runbooks.
```

No change to agent topology, no change to confidence math — purely a
prompt-hygiene fix.

## After the fix

Re-running the same 20 queries with the patched prompt (clean
like-for-like 70B judge, no parse failures):

| Difficulty | Grounded % (before, 70B) | Grounded % (after, 70B) | Δ |
|---|---|---|---|
| Easy | 20 % | 40 % | +20 |
| Medium | 20 % | 80 % | +60 |
| Hard | 0 % | 40 % | **+40** |
| Composite | 20 % | 80 % | +60 |
| **Overall** | **15.0 %** | **60.0 %** | **+45** |

All 20/20 queries returned parseable judgments (vs 17/20 on the earlier
8B run). Inspection of the after-fix `unsupported_claim` column
confirms the similarity-score leak is **completely gone** — no judged
diagnosis contains the phrase "similarity score" or "runbook patterns"
in the after-fix CSV. The remaining `unsupported_claim` entries are
legitimate inferences the strict binary judge penalises (e.g.
*"The load average of 45 on an 8-core box also suggests the system is
under heavy load"* — a reasonable reading of the alert itself that the
runbooks don't literally assert verbatim; see "Judge calibration"
below).

Context relevance (measured on retrieved chunks, independent of the
generator) is **identical** to before-fix — retrieval is upstream of
the prompt, so the fix shouldn't move it, and it didn't:

| Metric | Before (70B) | After (70B) |
|---|---|---|
| Mean chunk relevance | 0.7758 | 0.7758 |
| % chunks ≥ 0.7 useful | 91.67 % | 91.67 % |

This stability is itself a useful signal: it rules out the
counter-hypothesis that the Maven prompt fix somehow disturbed
retrieval. Every point of the groundedness gain is attributable to the
generator, not the retriever.

### Cross-model consistency check (8B vs 70B)

The initial after-fix re-run used `llama-3.1-8b-instant` because the
70B daily token quota was exhausted. Once TPD reset we re-ran on 70B
to get a clean like-for-like comparison:

| Metric | Before (70B) | After (8B) | **After (70B) — primary** |
|---|---|---|---|
| Groundedness | 15.0 % | 58.82 % (17/20 judged) | **60.0 % (20/20 judged)** |
| Context relevance (mean) | 0.7758 | 0.8267 | **0.7758** |
| Context relevance (≥ 0.7) | 91.67 % | 96.67 % | **91.67 %** |

The 8B number (58.82 %) was within 1.2 points of the 70B number
(60.0 %), which independently validates the 8B result. Context
relevance on 8B drifted slightly upward because the 8B judge is
somewhat more lenient in scoring chunk usefulness — that's a pure
judge-model artifact, not a retrieval change, exactly as the 70B
re-run demonstrates by returning to the before-fix values.

## Methodology note — model used per run

All three reported numbers (before-fix, after-fix on 8B, after-fix on
70B) were gathered in that order:

| Run | Model | Reason |
|---|---|---|
| Before-fix | `llama-3.3-70b-versatile` (70B) | Production default — baseline measurement. |
| After-fix (initial) | `llama-3.1-8b-instant` (8B) | 70B daily token quota was exhausted by the time the fix was applied; 8B runs against a separate free-tier quota bucket, so we could still validate the fix direction. |
| After-fix (clean) | `llama-3.3-70b-versatile` (70B) | Re-run after TPD reset to produce a like-for-like primary result. **This is the headline number reported above.** |

The 8B run is retained in the artifact set
([groundedness_after_fix.csv](../eval/results/groundedness_after_fix.csv))
as a **cross-model consistency check** — it independently corroborated
the 70B result within 1.2 points. If you want to reproduce the clean
70B numbers:

```bash
cd NEXUSHEAL
python -m eval.reliability_groundedness --suffix _after_fix_70b
python -m eval.reliability_context --suffix _after_fix_70b
```

## Sanity check — did the diagnoses just get shorter / blander?

A skeptical reading of "15 % → 60 %" is: *"Maybe the fix just made the
LLM generate shorter, safer, vaguer diagnoses, and a strict binary judge
rewards blandness."* We checked the actual text on the clean 70B run.

**Length comparison** (word count of `diagnosis` field, same 20 queries
judged in both runs):

| | Before fix (70B) | After fix (70B) | Δ |
|---|---|---|---|
| Mean words / diagnosis | 60.5 | **63.2** | **+2.8 (+4.6 %)** |
| Median | 61.5 | 66.0 | +4.5 |
| Per-query mean Δ (paired) | — | — | +2.8 words |
| Per-query Δ range (paired) | — | — | −12 to +21 words |

**The after-fix diagnoses are not shorter — they are slightly longer.**
The removed-leak content ("The average similarity score of 0.81
suggests a strong match…") was replaced with more substantive runbook-
grounded content, not trimmed away. The "maybe it just got blander"
hypothesis is refuted by the data: the model used the freed space to
say more about the actual runbook, not to hedge.

(The earlier 8B re-run *did* show a −21 % shortening. That was an 8B-
specific artifact — smaller models tend to truncate rather than expand
when given a "stick to the runbook" instruction. The clean 70B number
is the one the milestone report uses.)

**Leak-phrase occurrence** (exact string match for `"similarity score"`
or `"runbook pattern"` in the diagnosis body):

| | Before fix (70B) | After fix (70B) |
|---|---|---|
| Diagnoses containing either phrase | **16 / 20 (80 %)** | **3 / 20 (15 %)** |
| Diagnoses containing `"similarity score"` specifically | **~16 / 20** | **0 / 20** |

All 3 residual matches in the after-fix column use *"runbook pattern"*
as an honest reference to runbook content itself — for example:

- Q09: *"…matches the runbook pattern for a disk full alert, suggesting
  that the root cause is likely log file growth."*
- Q19: *"…matches the Network Latency runbook pattern, suggesting
  potential issues with network congestion…"*
- Q34: *"…matches the runbook pattern of a queue overflow due to
  consumer lag or producer spike."*

These are not fabricated telemetry statements; they are pointers at
the retrieved runbook by name. The leak phrase *"similarity score"*
disappears entirely (16 → 0).

**Side-by-side example** (query Q28 on 70B, paired before vs after):

> **Before** (63 words): *"The alert pattern matches the API Timeout
> runbook, with 45s query times and cascading 504s downstream,
> indicating a slow database query due to a missing index on the users
> table. **The average similarity score of 0.72** and the mention of a
> similar past incident INC-2024-012 support this diagnosis. **The
> high severity and specific details in the alert also contribute to
> the confidence in this diagnosis.**"*
>
> **After** (77 words, +14): *"The alert indicates a missing index on
> the users table, which is a common root cause of slow database
> queries, and this matches the pattern described in the API Timeout
> runbook. The slow queries led to cascading 504s downstream, which is
> consistent with the expected behavior when database queries exceed
> timeout thresholds. The runbook provides a clear remediation step to
> add a missing index, which supports this diagnosis."*

The fabricated similarity score is gone; the self-congratulatory
hedging about severity is gone; in their place is a more precise
description of the actual failure chain grounded in the runbook's
remediation section. The after-fix diagnosis is longer AND more
grounded.

**Verdict: the groundedness gain is real content improvement, not
blandness.** The shortness hypothesis is refuted by the numbers. The
fix removed fabricated content and the model replaced it with more
runbook-grounded content — exactly the intended effect.

## Judge calibration — a known limitation of LLM-as-judge

Even after the fix, groundedness is below 80 %. A qualitative review of
the still-ungrounded cases shows that **a meaningful fraction are
legitimate inferences the judge is penalizing too strictly**. Examples:

- **Q01** — "the system is under heavy load, and the thread pool is
  likely exhausted" → the *Common Root Causes* section of
  [runbook_api_timeout.md](../knowledge_base/runbook_api_timeout.md)
  explicitly lists "Thread pool exhaustion" as cause #3.
- **Q11** — "writes failing and 'No space left on device' errors" →
  literally the first line of *Alert Pattern* in
  [runbook_disk_full.md](../knowledge_base/runbook_disk_full.md).
- **Q24** — "the cert-manager pod is crashlooping, which suggests a
  problem with the certificate renewal process" → supported by both
  [runbook_ssl_expired.md](../knowledge_base/runbook_ssl_expired.md)
  (cert-manager failure listed) and
  [runbook_pod_crash.md](../knowledge_base/runbook_pod_crash.md)
  (CrashLoopBackOff causes).

A binary `{grounded: 0, grounded: 1}` judge applied with a "EVERY claim
must be supported" instruction is, by design, **strict**. It will
penalize diagnoses that paraphrase or combine multiple runbook facts
even when the combined claim is correct.

The reported **58.82 % grounded is therefore a lower bound** on true
groundedness post-fix. A production-grade judge would need a
rubric-scored response (`fully / partially / not grounded`) and
multiple judge runs for reliability, which is future work beyond this
milestone's scope.

## Why this matters

Our reliability check **did its job**. It caught a
hallucination-adjacent bug that:

- **Retrieval metrics would never have caught** — Hit@3 is 0.95, MRR
  is 0.89. The retriever was working fine. The bug was in the
  generator.
- **The end-to-end pytest suite would never have caught** — all five
  tests pass on both the before-fix and after-fix code. The pytest
  asserts that `diagnosis` is a non-empty string; it does not and
  cannot assert that the content is grounded.
- **A human reading a single diagnosis would probably miss** — the
  similarity-score phrasing sounds authoritative. You'd only notice
  when comparing many outputs and realising the same number was being
  re-quoted across unrelated incidents.

The lesson for the milestone: **LLM-as-judge reliability checks are a
necessary complement to standard IR metrics**, not a substitute. They
surface failure modes that neither retrieval metrics nor unit tests
can see, because they operate at the generation boundary.

## Artifacts

| File | Content |
|---|---|
| [eval/results/groundedness.csv](../eval/results/groundedness.csv) | 20 queries, before-fix on 70B — contains the leaking diagnoses |
| [eval/results/groundedness_summary.json](../eval/results/groundedness_summary.json) | Before-fix aggregate (15.0 %) + top unsupported claims |
| [eval/results/groundedness_after_fix.csv](../eval/results/groundedness_after_fix.csv) | 8B cross-model consistency check — 58.82 %, 17/20 judged |
| [eval/results/groundedness_summary_after_fix.json](../eval/results/groundedness_summary_after_fix.json) | 8B after-fix aggregate |
| [**eval/results/groundedness_after_fix_70b.csv**](../eval/results/groundedness_after_fix_70b.csv) | **Clean 70B after-fix — 60.0 %, 20/20 judged — headline number** |
| [eval/results/groundedness_summary_after_fix_70b.json](../eval/results/groundedness_summary_after_fix_70b.json) | 70B after-fix aggregate (primary) |
| [eval/results/context_relevance_summary.json](../eval/results/context_relevance_summary.json) | Context relevance before-fix on 70B (0.7758 / 91.67 %) |
| [eval/results/context_relevance_summary_after_fix.json](../eval/results/context_relevance_summary_after_fix.json) | 8B after-fix context relevance (0.8267 / 96.67 %, judge-model drift) |
| [eval/results/context_relevance_summary_after_fix_70b.json](../eval/results/context_relevance_summary_after_fix_70b.json) | 70B after-fix context relevance (0.7758 / 91.67 %, identical to before) |
| [agents/maven.py](../agents/maven.py) | Fix is live in the production agent |
