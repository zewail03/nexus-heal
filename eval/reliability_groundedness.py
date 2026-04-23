"""
Reliability check 5B — Groundedness.

For 20 stratified queries (5 per difficulty bucket, spanning all 10 runbook
types) we invoke the full NEXUS-HEAL pipeline, capture the generated
diagnosis and the chunks Maven retrieved, and ask Groq (LLM-as-judge)
whether *every factual claim* in the diagnosis is supported by the context.

Outputs
-------
    eval/results/groundedness.csv          -- one row per query
    eval/results/groundedness_summary.json -- aggregate stats + top unsupported claims

Usage
-----
    python -m eval.reliability_groundedness
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langchain_groq import ChatGroq  # noqa: E402

from config import GROQ_API_KEY, LLM_MODEL  # noqa: E402
from graph.pipeline import nexus_graph  # noqa: E402
from rag.vectorstore import setup_vectorstore  # noqa: E402


EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
QUERIES_PATH = EVAL_DIR / "labeled_queries.json"

PER_DIFFICULTY = 5  # 5 easy + 5 medium + 5 hard + 5 composite = 20 total


PROMPT_TEMPLATE = """You are checking if a diagnosis is grounded in retrieved context.

Query: {query}
Retrieved context:
{chunks_joined}

Generated diagnosis: {diagnosis}

Is EVERY factual claim in the diagnosis supported by the context?
Return ONLY valid JSON:
{{"grounded": 1, "unsupported_claim": null}}
OR
{{"grounded": 0, "unsupported_claim": "the specific claim not in context"}}"""


def stratified_sample(queries: list[dict], per_diff: int = PER_DIFFICULTY) -> list[dict]:
    """Pick `per_diff` queries from each difficulty, alternating halves so the
    sample spans all 10 runbook types rather than clustering on the first 5."""
    buckets = defaultdict(list)
    for q in queries:
        buckets[q["difficulty"]].append(q)
    # easy + hard come from the first half of each bucket (runbooks 1-5),
    # medium + composite from the second half (runbooks 6-10) -> full coverage.
    sampled: list[dict] = []
    sampled.extend(buckets.get("easy", [])[:per_diff])
    sampled.extend(buckets.get("medium", [])[per_diff : per_diff * 2])
    sampled.extend(buckets.get("hard", [])[:per_diff])
    sampled.extend(buckets.get("composite", [])[per_diff : per_diff * 2])
    return sampled


def _build_initial_state(alert_id: str, alert_raw: str) -> dict:
    """Same shape that api/server.py::analyze_alert constructs."""
    return {
        "alert_id": alert_id,
        "alert_raw": alert_raw,
        "alert_severity": "",
        "alert_type": "",
        "alert_category": "",
        "confidence_classify": 0.0,
        "retrieved_docs": [],
        "diagnosis": "",
        "root_cause": "",
        "confidence_diagnose": 0.0,
        "similar_incidents": [],
        "fix_plan": [],
        "fix_commands": [],
        "rollback_plan": "",
        "estimated_time": "",
        "human_approved": False,
        "execution_status": "pending",
        "validation_result": "",
        "final_message": "",
        "iteration_count": 0,
        "error": None,
    }


def _parse_judge_json(text: str) -> dict | None:
    """Parse a judge reply, tolerating markdown code fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or "grounded" not in obj:
        return None
    obj["grounded"] = int(obj["grounded"])
    obj.setdefault("unsupported_claim", None)
    if obj["grounded"] not in (0, 1):
        return None
    return obj


def judge_groundedness(
    llm: ChatGroq, query: str, chunks_joined: str, diagnosis: str, max_retries: int = 2
) -> dict | None:
    prompt = PROMPT_TEMPLATE.format(
        query=query, chunks_joined=chunks_joined, diagnosis=diagnosis
    )
    for attempt in range(max_retries + 1):
        try:
            resp = llm.invoke(prompt)
            parsed = _parse_judge_json(resp.content)
            if parsed is not None:
                return parsed
        except Exception as e:
            print(f"      [retry {attempt}] Groq error: {type(e).__name__}: {e}")
            time.sleep(1.0)
            continue
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM-as-judge groundedness check")
    parser.add_argument(
        "--suffix",
        default="",
        help="Optional suffix for output files (e.g. '_after_fix' -> groundedness_after_fix.csv).",
    )
    args = parser.parse_args()
    suffix = args.suffix

    print("[5B] Ensuring ChromaDB is populated...")
    setup_vectorstore()

    with QUERIES_PATH.open(encoding="utf-8") as f:
        queries = json.load(f)["queries"]

    if not GROQ_API_KEY:
        print("[5B] ERROR — GROQ_API_KEY not set in environment.")
        sys.exit(1)

    sample = stratified_sample(queries, PER_DIFFICULTY)
    print(f"[5B] Sampled {len(sample)} queries ({PER_DIFFICULTY} per difficulty).")
    runbooks_covered = {q["alert_type"] for q in sample}
    print(f"[5B] Runbook types in sample: {len(runbooks_covered)}/10 — "
          f"{sorted(runbooks_covered)}")

    judge = ChatGroq(model=LLM_MODEL, temperature=0, api_key=GROQ_API_KEY)

    rows: list[dict] = []
    by_diff: dict[str, list[int]] = defaultdict(list)
    unsupported: list[str] = []

    t_start = time.perf_counter()
    for i, q in enumerate(sample, start=1):
        print(f"[5B] ({i}/{len(sample)}) {q['id']} [{q['difficulty']}]  {q['alert_type']}")
        t0 = time.perf_counter()
        state = nexus_graph.invoke(_build_initial_state(f"GND-{q['id']}", q["query"]))
        pipeline_secs = time.perf_counter() - t0

        diagnosis = state.get("diagnosis", "")
        retrieved = state.get("retrieved_docs", [])
        chunks_joined = "\n\n---\n\n".join(d.get("content", "") for d in retrieved)

        judged = judge_groundedness(judge, q["query"], chunks_joined, diagnosis)
        if judged is None:
            print("      JUDGE FAILED after retries — skipping this query")
            continue

        grounded = int(judged["grounded"])
        claim = judged.get("unsupported_claim")
        if isinstance(claim, str):
            claim = claim.strip() or None
        by_diff[q["difficulty"]].append(grounded)
        if grounded == 0 and claim:
            unsupported.append(claim)

        rows.append({
            "query_id": q["id"],
            "difficulty": q["difficulty"],
            "alert_type": q["alert_type"],
            "query": q["query"],
            "diagnosis": diagnosis,
            "num_retrieved": len(retrieved),
            "grounded": grounded,
            "unsupported_claim": claim or "",
            "pipeline_seconds": round(pipeline_secs, 2),
        })
        print(f"      grounded={grounded}  pipeline={pipeline_secs:.1f}s  "
              + (f'unsupported: "{claim}"' if (grounded == 0 and claim) else ""))

    elapsed = time.perf_counter() - t_start

    # -- aggregate ----------------------------------------------------------
    flat = [r["grounded"] for r in rows]
    pct_grounded = round(100.0 * statistics.mean(flat), 2) if flat else 0.0
    top_unsupported = [c for c, _ in Counter(unsupported).most_common(3)]
    summary = {
        "num_sampled": len(sample),
        "num_judged": len(rows),
        "overall": {
            "pct_grounded": pct_grounded,
            "num_ungrounded": sum(1 for g in flat if g == 0),
        },
        "by_difficulty": {
            diff: {
                "pct_grounded": round(100.0 * statistics.mean(vals), 2) if vals else 0.0,
                "n": len(vals),
            }
            for diff, vals in by_diff.items()
        },
        "top_unsupported_claims": top_unsupported,
        "wall_clock_seconds": round(elapsed, 1),
        "model": LLM_MODEL,
    }

    # -- write outputs ------------------------------------------------------
    csv_path = RESULTS_DIR / f"groundedness{suffix}.csv"
    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    json_path = RESULTS_DIR / f"groundedness_summary{suffix}.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 60)
    print("  Groundedness — 5B")
    print("=" * 60)
    print(f"  queries judged      : {len(rows)}/{len(sample)}")
    print(f"  % grounded (overall): {pct_grounded}%")
    print("\n  By difficulty:")
    for diff, stats in summary["by_difficulty"].items():
        print(f"    [{diff:9}]  pct_grounded={stats['pct_grounded']}%  (n={stats['n']})")
    if top_unsupported:
        print("\n  Top unsupported claims:")
        for c in top_unsupported:
            print(f"    - {c}")
    print(f"\n  wall clock          : {elapsed:.1f}s")
    print(f"\n  CSV   : {csv_path}")
    print(f"  JSON  : {json_path}")


if __name__ == "__main__":
    main()
