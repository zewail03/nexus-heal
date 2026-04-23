"""
Reliability check 5A — Context Relevance.

For each of the 40 labeled queries, we retrieve the top-3 chunks using the
production RAG config, then ask Groq to judge — on a 0.0-1.0 scale — whether
each (query, chunk) pair is actually useful for diagnosing that query.

This is an LLM-as-judge check. It complements the hit/precision/recall
metrics: a chunk can hit the correct runbook yet still be a weak match at
the passage level (e.g., the retrieval surfaced the *Similar Past Incidents*
section when the user really needed the *Diagnosis Steps*).

Outputs
-------
    eval/results/context_relevance.csv            -- one row per (query, chunk)
    eval/results/context_relevance_summary.json   -- aggregate stats

Usage
-----
    python -m eval.reliability_context
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langchain_groq import ChatGroq  # noqa: E402

from config import GROQ_API_KEY, LLM_MODEL, RAG_TOP_K  # noqa: E402
from rag.retriever import retrieve_docs  # noqa: E402
from rag.vectorstore import setup_vectorstore  # noqa: E402


EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
QUERIES_PATH = EVAL_DIR / "labeled_queries.json"

# Threshold for "genuinely useful" chunks. 0.7 is the cutoff the milestone
# rubric asks us to report; tweak here if you want a different definition.
USEFUL_THRESHOLD = 0.7


PROMPT_TEMPLATE = """You are evaluating retrieval quality for an IT incident response system.

Query: {query}
Retrieved context: {chunk}

Is this context relevant and useful for diagnosing this query?
Rate 0.0 (completely irrelevant) to 1.0 (directly answers the query).
Return ONLY the number, no explanation."""


def _parse_float(text: str) -> float | None:
    """Extract the first float from a (possibly noisy) LLM reply."""
    import re

    # Strip markdown / backticks / whitespace
    cleaned = text.strip().replace("`", "")
    # First token that parses as a float in [0, 1]
    for tok in re.findall(r"[0-9]*\.?[0-9]+", cleaned):
        try:
            val = float(tok)
        except ValueError:
            continue
        if 0.0 <= val <= 1.0:
            return val
    return None


def judge_relevance(llm: ChatGroq, query: str, chunk: str, max_retries: int = 2) -> float | None:
    """Call Groq to rate (query, chunk) relevance. Retry on unparseable replies."""
    prompt = PROMPT_TEMPLATE.format(query=query, chunk=chunk)
    for attempt in range(max_retries + 1):
        try:
            resp = llm.invoke(prompt)
            score = _parse_float(resp.content)
            if score is not None:
                return score
        except Exception as e:
            print(f"      [retry {attempt}] Groq error: {type(e).__name__}: {e}")
            time.sleep(1.0)
            continue
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM-as-judge context relevance check")
    parser.add_argument(
        "--suffix",
        default="",
        help="Optional suffix for output files (e.g. '_after_fix' -> context_relevance_after_fix.csv).",
    )
    args = parser.parse_args()
    suffix = args.suffix

    print("[5A] Ensuring ChromaDB is populated...")
    setup_vectorstore()

    with QUERIES_PATH.open(encoding="utf-8") as f:
        queries = json.load(f)["queries"]

    if not GROQ_API_KEY:
        print("[5A] ERROR — GROQ_API_KEY not set in environment.")
        sys.exit(1)

    llm = ChatGroq(model=LLM_MODEL, temperature=0, api_key=GROQ_API_KEY)

    rows: list[dict] = []
    agg_scores: list[float] = []
    per_difficulty: dict[str, list[float]] = defaultdict(list)
    per_query_mean: list[tuple[str, str, float]] = []  # (id, difficulty, mean)

    total = len(queries)
    t_start = time.perf_counter()

    for i, q in enumerate(queries, start=1):
        docs = retrieve_docs(query=q["query"], alert_type=q["alert_type"], top_k=RAG_TOP_K)
        print(f"[5A] ({i}/{total}) {q['id']} [{q['difficulty']}] — judging {len(docs)} chunks...")

        per_chunk_scores: list[float] = []
        for rank, doc in enumerate(docs, start=1):
            score = judge_relevance(llm, q["query"], doc["content"])
            if score is None:
                print(f"      rank {rank}: FAILED to parse judge reply after retries")
                continue
            per_chunk_scores.append(score)
            agg_scores.append(score)
            per_difficulty[q["difficulty"]].append(score)

            rows.append({
                "query_id": q["id"],
                "difficulty": q["difficulty"],
                "alert_type": q["alert_type"],
                "query": q["query"],
                "rank": rank,
                "chunk_source": doc.get("source", ""),
                "retrieval_score": round(doc.get("score", 0.0), 4),
                "judge_relevance": round(score, 2),
                "chunk_preview": doc["content"][:120].replace("\n", " "),
            })

        query_mean = statistics.mean(per_chunk_scores) if per_chunk_scores else 0.0
        per_query_mean.append((q["id"], q["difficulty"], query_mean))
        print(f"      chunks mean = {query_mean:.2f}")

    elapsed = time.perf_counter() - t_start

    # -- aggregate stats ----------------------------------------------------
    mean_overall = round(statistics.mean(agg_scores), 4) if agg_scores else 0.0
    pct_useful = round(
        100.0 * sum(1 for s in agg_scores if s >= USEFUL_THRESHOLD) / max(1, len(agg_scores)), 2
    )
    summary = {
        "num_queries": total,
        "num_chunks_judged": len(agg_scores),
        "threshold_useful": USEFUL_THRESHOLD,
        "overall": {
            "mean_chunk_relevance": mean_overall,
            "pct_chunks_useful_ge_threshold": pct_useful,
        },
        "by_difficulty": {
            diff: {
                "mean_chunk_relevance": round(statistics.mean(vals), 4),
                "pct_chunks_useful_ge_threshold": round(
                    100.0 * sum(1 for s in vals if s >= USEFUL_THRESHOLD) / max(1, len(vals)), 2
                ),
                "n_chunks": len(vals),
            }
            for diff, vals in per_difficulty.items()
        },
        "wall_clock_seconds": round(elapsed, 1),
        "model": LLM_MODEL,
    }

    # -- write outputs ------------------------------------------------------
    csv_path = RESULTS_DIR / f"context_relevance{suffix}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    json_path = RESULTS_DIR / f"context_relevance_summary{suffix}.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # -- console report -----------------------------------------------------
    print("\n" + "=" * 60)
    print("  Context Relevance — 5A")
    print("=" * 60)
    print(f"  chunks judged      : {summary['num_chunks_judged']}  "
          f"({len(queries)} queries x top_k={RAG_TOP_K})")
    print(f"  mean relevance     : {mean_overall:.4f}")
    print(f"  % chunks >= {USEFUL_THRESHOLD} : {pct_useful}%")
    print("\n  By difficulty:")
    for diff, stats in summary["by_difficulty"].items():
        print(f"    [{diff:9}]  mean={stats['mean_chunk_relevance']:.4f}  "
              f">={USEFUL_THRESHOLD}: {stats['pct_chunks_useful_ge_threshold']}%  "
              f"(n={stats['n_chunks']})")
    print(f"\n  wall clock         : {elapsed:.1f}s")
    print(f"\n  Per-chunk CSV      : {csv_path}")
    print(f"  Summary JSON       : {json_path}")


if __name__ == "__main__":
    main()
