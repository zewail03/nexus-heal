"""
Reliability check 5C — Rubric-scored groundedness with majority vote.

Improves on the binary {0,1} judge in `reliability_groundedness.py`.
Each diagnosis is graded on a 3-level rubric:

    * fully        (1.0) — every factual claim is supported by context.
    * partial      (0.5) — most of the diagnosis is supported, but at
                           least one claim is an inference not explicit
                           in the context (often legitimate).
    * not_grounded (0.0) — contains a claim that plainly contradicts or
                           is absent from the retrieved context.

Each query is judged N=3 times with temperature=0 (but with the judge
re-invoked fresh each call, Groq's token sampling still produces some
variance). The final grade is the **majority vote** across the 3
runs; ties favour the stricter grade.

By re-using the diagnoses already captured in
`eval/results/groundedness_after_fix_70b.csv`, we only spend LLM tokens
on the judge — no pipeline re-run, no Sentinel/Maven/Healer calls.

Outputs
-------
    eval/results/groundedness_rubric.csv            -- per-query rows
    eval/results/groundedness_rubric_summary.json   -- aggregate stats

Usage
-----
    python -m eval.reliability_groundedness_rubric
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


EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Default source for diagnoses is the clean 70B after-fix run.
DEFAULT_INPUT_CSV = RESULTS_DIR / "groundedness_after_fix_70b.csv"

N_JUDGE_RUNS = 3  # per query — majority vote

GRADE_SCORE = {"fully": 1.0, "partial": 0.5, "not_grounded": 0.0}
# When votes tie (e.g. fully/partial/partial vs fully/fully/partial),
# majority_vote() picks by count; on a 3-way tie we fall back to the
# stricter grade so we never over-report groundedness.
STRICTNESS_ORDER = ["not_grounded", "partial", "fully"]


PROMPT_TEMPLATE = """You are grading whether a diagnosis is grounded in retrieved context.

Query: {query}
Retrieved context:
{chunks_joined}

Generated diagnosis: {diagnosis}

Grade the diagnosis on this rubric:
- "fully": every factual claim is directly supported by the context.
- "partial": most of the diagnosis is supported, but at least one claim is an inference not explicit in the context (may still be reasonable).
- "not_grounded": contains a claim that contradicts or is plainly absent from the context.

Return ONLY valid JSON:
{{"grade": "fully"|"partial"|"not_grounded", "unsupported_claim": "..." or null}}

If grade is "fully", unsupported_claim MUST be null."""


def _parse_judge_json(text: str) -> dict | None:
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
    grade = obj.get("grade")
    if grade not in GRADE_SCORE:
        return None
    obj.setdefault("unsupported_claim", None)
    return obj


def judge_once(llm: ChatGroq, query: str, chunks: str, diagnosis: str, max_retries: int = 2) -> dict | None:
    prompt = PROMPT_TEMPLATE.format(query=query, chunks_joined=chunks, diagnosis=diagnosis)
    for attempt in range(max_retries + 1):
        try:
            resp = llm.invoke(prompt)
            parsed = _parse_judge_json(resp.content)
            if parsed is not None:
                return parsed
        except Exception as e:
            print(f"        [retry {attempt}] Groq error: {type(e).__name__}: {e}")
            time.sleep(1.0)
    return None


def majority_vote(grades: list[str]) -> str:
    """Strictest-wins tie-break: if two grades are tied in count, pick the
    one earlier in STRICTNESS_ORDER (i.e. stricter)."""
    counts = Counter(grades)
    top_count = max(counts.values())
    leaders = [g for g, c in counts.items() if c == top_count]
    if len(leaders) == 1:
        return leaders[0]
    for g in STRICTNESS_ORDER:
        if g in leaders:
            return g
    return leaders[0]  # defensive


def load_cases(csv_path: Path) -> list[dict]:
    """The input CSV has diagnosis text but not the original retrieved
    chunks (the old groundedness script didn't persist them). We need
    both for the rubric judge, so we re-load the labeled_queries.json
    + re-retrieve via the production RAG — retrieval is deterministic
    on the saved ChromaDB so this reproduces the chunks exactly."""
    # Load saved diagnoses
    with csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Load original queries
    from eval.reliability_groundedness import stratified_sample  # reuse
    from rag.retriever import retrieve_docs
    from rag.vectorstore import setup_vectorstore
    from config import RAG_TOP_K

    setup_vectorstore()
    with (EVAL_DIR / "labeled_queries.json").open(encoding="utf-8") as f:
        queries = json.load(f)["queries"]
    sample = {q["id"]: q for q in stratified_sample(queries)}

    cases: list[dict] = []
    for row in rows:
        q = sample.get(row["query_id"])
        if q is None:
            continue
        docs = retrieve_docs(query=q["query"], alert_type=q["alert_type"], top_k=RAG_TOP_K)
        chunks = "\n\n---\n\n".join(d.get("content", "") for d in docs)
        cases.append({
            "query_id": row["query_id"],
            "difficulty": row["difficulty"],
            "alert_type": row["alert_type"],
            "query": q["query"],
            "chunks_joined": chunks,
            "diagnosis": row["diagnosis"],
            "binary_grounded": int(row["grounded"]),  # carry for comparison
        })
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Rubric-scored groundedness judge (N=3 majority vote)")
    parser.add_argument("--input", default=str(DEFAULT_INPUT_CSV),
                        help="CSV of (query_id, difficulty, alert_type, query, diagnosis, grounded) to re-judge.")
    parser.add_argument("--runs", type=int, default=N_JUDGE_RUNS,
                        help=f"Number of judge runs per query (default {N_JUDGE_RUNS}). Majority vote across runs.")
    parser.add_argument("--suffix", default="", help="Suffix for output files.")
    args = parser.parse_args()

    if not GROQ_API_KEY:
        print("[5C] ERROR — GROQ_API_KEY not set.")
        sys.exit(1)

    print(f"[5C] Loading diagnoses from {args.input}")
    cases = load_cases(Path(args.input))
    print(f"[5C] Loaded {len(cases)} cases. Re-judging on {LLM_MODEL} with N={args.runs} runs per query.")

    llm = ChatGroq(model=LLM_MODEL, temperature=0, api_key=GROQ_API_KEY)

    rows: list[dict] = []
    by_diff_scores: dict[str, list[float]] = defaultdict(list)
    overall_scores: list[float] = []
    unsupported_claims: list[str] = []

    t_start = time.perf_counter()

    for i, case in enumerate(cases, start=1):
        print(f"[5C] ({i}/{len(cases)}) {case['query_id']} [{case['difficulty']}]  {case['alert_type']}")
        run_grades: list[str] = []
        run_claims: list[str] = []
        for run_idx in range(args.runs):
            parsed = judge_once(llm, case["query"], case["chunks_joined"], case["diagnosis"])
            if parsed is None:
                print(f"      run {run_idx + 1}: JUDGE FAILED after retries")
                continue
            run_grades.append(parsed["grade"])
            if parsed.get("unsupported_claim"):
                run_claims.append(parsed["unsupported_claim"])

        if not run_grades:
            print("      all runs failed — skipping")
            continue

        final_grade = majority_vote(run_grades)
        final_score = GRADE_SCORE[final_grade]
        overall_scores.append(final_score)
        by_diff_scores[case["difficulty"]].append(final_score)

        # Record a representative unsupported_claim if the final verdict
        # was not 'fully'. Prefer the claim that appeared in the run
        # whose grade matches the majority.
        chosen_claim = ""
        if final_grade != "fully" and run_claims:
            chosen_claim = run_claims[0]
            unsupported_claims.append(chosen_claim)

        rows.append({
            "query_id": case["query_id"],
            "difficulty": case["difficulty"],
            "alert_type": case["alert_type"],
            "query": case["query"],
            "diagnosis": case["diagnosis"],
            "run_grades": "|".join(run_grades),
            "final_grade": final_grade,
            "final_score": final_score,
            "binary_grounded_was": case["binary_grounded"],
            "unsupported_claim": chosen_claim,
        })
        print(f"      votes={run_grades}  ->  {final_grade} ({final_score})")

    elapsed = time.perf_counter() - t_start

    # -- aggregate ----------------------------------------------------------
    mean_rubric = round(statistics.mean(overall_scores), 4) if overall_scores else 0.0
    grade_counts = Counter(r["final_grade"] for r in rows)
    binary_rate_previous = round(
        100.0 * statistics.mean([r["binary_grounded_was"] for r in rows]), 2
    ) if rows else 0.0

    top_claims = [c for c, _ in Counter(unsupported_claims).most_common(3)]

    summary = {
        "num_judged": len(rows),
        "runs_per_query": args.runs,
        "model": LLM_MODEL,
        "rubric_mean_score_0_to_1": mean_rubric,
        "rubric_mean_pct": round(mean_rubric * 100, 2),
        "grade_counts": dict(grade_counts),
        "pct_fully": round(100.0 * grade_counts.get("fully", 0) / max(1, len(rows)), 2),
        "pct_partial": round(100.0 * grade_counts.get("partial", 0) / max(1, len(rows)), 2),
        "pct_not_grounded": round(100.0 * grade_counts.get("not_grounded", 0) / max(1, len(rows)), 2),
        "by_difficulty": {
            diff: {
                "mean_score": round(statistics.mean(vals), 4) if vals else 0.0,
                "n": len(vals),
            }
            for diff, vals in by_diff_scores.items()
        },
        "previous_binary_pct_grounded": binary_rate_previous,
        "top_unsupported_claims": top_claims,
        "wall_clock_seconds": round(elapsed, 1),
    }

    # -- write outputs ------------------------------------------------------
    csv_path = RESULTS_DIR / f"groundedness_rubric{args.suffix}.csv"
    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    json_path = RESULTS_DIR / f"groundedness_rubric_summary{args.suffix}.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 60)
    print("  Groundedness — Rubric (5C)")
    print("=" * 60)
    print(f"  queries judged        : {len(rows)}  (runs per query: {args.runs})")
    print(f"  rubric mean (0-1)     : {mean_rubric}")
    print(f"  rubric mean (%)       : {round(mean_rubric * 100, 2)}%")
    print(f"  fully / partial / not : "
          f"{grade_counts.get('fully', 0)} / "
          f"{grade_counts.get('partial', 0)} / "
          f"{grade_counts.get('not_grounded', 0)}")
    print(f"  binary judge was      : {binary_rate_previous}% grounded")
    print("\n  By difficulty (mean score):")
    for diff, stats in summary["by_difficulty"].items():
        print(f"    [{diff:9}]  mean={stats['mean_score']:.4f}  (n={stats['n']})")
    if top_claims:
        print("\n  Top residual unsupported claims:")
        for c in top_claims:
            print(f"    - {c}")
    print(f"\n  wall clock           : {elapsed:.1f}s")
    print(f"\n  CSV   : {csv_path}")
    print(f"  JSON  : {json_path}")


if __name__ == "__main__":
    main()
