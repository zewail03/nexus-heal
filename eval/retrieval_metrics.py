"""
Retrieval-quality evaluation for NEXUS-HEAL RAG.

Loads eval/labeled_queries.json, runs each query through the current ChromaDB
retriever, and computes standard IR metrics against the ground-truth relevant
runbooks:
    - Hit@k        : did any relevant runbook appear in top-k?
    - Precision@k  : fraction of retrieved (unique) runbooks that are relevant
    - Recall@k     : fraction of ground-truth runbooks that were retrieved
    - MRR          : reciprocal rank of the first relevant chunk
    - NDCG@k       : ranking-aware score (binary relevance)

Granularity note
----------------
ChromaDB returns chunk-level hits, but relevance is labeled at the runbook
level (each runbook is chunked into several pieces). We compute MRR and NDCG
at the chunk level (ranking matters), and Precision/Recall/Hit at the
unique-runbook level (avoids double-counting chunks from the same runbook).

Usage
-----
    python -m eval.retrieval_metrics

Writes:
    eval/results/baseline_metrics.csv        -- per-query metrics
    eval/results/baseline_summary.json       -- aggregate metrics
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

# Make project root importable when invoked as a script
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.retriever import retrieve_docs  # noqa: E402
from rag.vectorstore import setup_vectorstore  # noqa: E402


EVAL_DIR = Path(__file__).resolve().parent
QUERIES_PATH = EVAL_DIR / "labeled_queries.json"
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# k values we report. Top-k=5 is larger than the app default (3) so we can
# report Hit@5 as an upper bound on what the retriever *could* surface.
K_VALUES = (1, 3, 5)


def hit_at_k(retrieved_sources: list[str], relevant: set[str], k: int) -> float:
    return 1.0 if set(retrieved_sources[:k]) & relevant else 0.0


def precision_at_k(retrieved_sources: list[str], relevant: set[str], k: int) -> float:
    """Unique-runbook precision: |unique retrieved ∩ relevant| / |unique retrieved|."""
    top = list(dict.fromkeys(retrieved_sources[:k]))  # dedupe, preserve order
    if not top:
        return 0.0
    hits = sum(1 for s in top if s in relevant)
    return hits / len(top)


def recall_at_k(retrieved_sources: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    top = set(retrieved_sources[:k])
    return len(top & relevant) / len(relevant)


def mrr(retrieved_sources: list[str], relevant: set[str]) -> float:
    """Reciprocal rank of the first chunk whose source runbook is relevant."""
    for i, src in enumerate(retrieved_sources, start=1):
        if src in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(retrieved_sources: list[str], relevant: set[str], k: int) -> float:
    """
    Binary-relevance NDCG with runbook-level dedup.

    Since many chunks share a source runbook, we dedupe: only the first chunk
    from each runbook contributes gain. This keeps NDCG bounded by 1.0 and
    matches the runbook-level relevance we defined in the ground truth.
    """
    seen: set[str] = set()
    gains: list[float] = []
    for s in retrieved_sources[:k]:
        if s in seen:
            gains.append(0.0)  # duplicate source — no additional relevance credit
            continue
        seen.add(s)
        gains.append(1.0 if s in relevant else 0.0)
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    # Ideal = relevant runbooks filling top slots (capped by k)
    ideal_hits = min(k, max(1, len(relevant)))
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
    return dcg / idcg if idcg > 0 else 0.0


def evaluate(queries: list[dict], top_k: int = max(K_VALUES)) -> tuple[list[dict], dict]:
    """Run every labeled query and return (per-query rows, aggregate summary)."""
    per_query_rows: list[dict] = []
    agg: dict[str, list[float]] = defaultdict(list)
    by_difficulty: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for q in queries:
        docs = retrieve_docs(query=q["query"], alert_type=q["alert_type"], top_k=top_k)
        retrieved_sources = [d.get("source", "") for d in docs]
        relevant = set(q["relevant_runbooks"])

        row = {
            "id": q["id"],
            "difficulty": q["difficulty"],
            "alert_type": q["alert_type"],
            "query": q["query"],
            "relevant": "|".join(sorted(relevant)),
            "retrieved_top_k": "|".join(retrieved_sources),
            "top1_score": docs[0]["score"] if docs else 0.0,
        }

        for k in K_VALUES:
            row[f"hit@{k}"] = hit_at_k(retrieved_sources, relevant, k)
            row[f"precision@{k}"] = precision_at_k(retrieved_sources, relevant, k)
            row[f"recall@{k}"] = recall_at_k(retrieved_sources, relevant, k)
            row[f"ndcg@{k}"] = ndcg_at_k(retrieved_sources, relevant, k)
            agg[f"hit@{k}"].append(row[f"hit@{k}"])
            agg[f"precision@{k}"].append(row[f"precision@{k}"])
            agg[f"recall@{k}"].append(row[f"recall@{k}"])
            agg[f"ndcg@{k}"].append(row[f"ndcg@{k}"])
            by_difficulty[q["difficulty"]][f"hit@{k}"].append(row[f"hit@{k}"])

        row["mrr"] = mrr(retrieved_sources, relevant)
        agg["mrr"].append(row["mrr"])
        by_difficulty[q["difficulty"]]["mrr"].append(row["mrr"])

        per_query_rows.append(row)

    summary = {
        "num_queries": len(queries),
        "top_k_evaluated": top_k,
        "overall": {metric: round(statistics.mean(vals), 4) for metric, vals in agg.items()},
        "by_difficulty": {
            diff: {metric: round(statistics.mean(vals), 4) for metric, vals in metrics.items()}
            for diff, metrics in by_difficulty.items()
        },
    }
    return per_query_rows, summary


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(summary: dict) -> None:
    print("\n" + "=" * 60)
    print(f"  NEXUS-HEAL retrieval eval  ({summary['num_queries']} queries)")
    print("=" * 60)
    print("\nOverall (mean across all queries):")
    for metric, val in summary["overall"].items():
        print(f"  {metric:<14} {val:.4f}")
    print("\nBy difficulty:")
    for diff, metrics in summary["by_difficulty"].items():
        print(f"  [{diff}]")
        for metric, val in metrics.items():
            print(f"    {metric:<14} {val:.4f}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run retrieval eval against current ChromaDB config")
    parser.add_argument(
        "--name",
        default="baseline",
        help="Output filename prefix under eval/results/ (e.g. 'baseline' or 'final'). "
             "Writes <name>_metrics.csv and <name>_summary.json.",
    )
    args = parser.parse_args()

    # Make sure the vectorstore exists / is populated
    print("[eval] Ensuring ChromaDB is populated...")
    setup_vectorstore()

    print(f"[eval] Loading queries from {QUERIES_PATH.name}")
    with QUERIES_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    queries = data["queries"]

    print(f"[eval] Running retrieval for {len(queries)} queries (top_k={max(K_VALUES)})...")
    rows, summary = evaluate(queries, top_k=max(K_VALUES))

    csv_path = RESULTS_DIR / f"{args.name}_metrics.csv"
    json_path = RESULTS_DIR / f"{args.name}_summary.json"
    write_csv(rows, csv_path)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print_summary(summary)
    print(f"[eval] Per-query CSV : {csv_path}")
    print(f"[eval] Summary JSON  : {json_path}")


if __name__ == "__main__":
    main()
