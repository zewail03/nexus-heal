"""
Hybrid BM25 + dense retrieval for NEXUS-HEAL.

Combines lexical (BM25Okapi) and semantic (cosine over MiniLM embeddings)
signals via Reciprocal Rank Fusion (RRF). RRF normalises by *rank*, not
score, so it's robust to BM25's open-ended score range vs cosine's
[0, 1] — the two legs cannot drown each other out.

Motivation
----------
Q07-class queries — natural-language descriptions with zero domain
vocabulary, like "Service becomes unresponsive after running for a day,
a manual restart fixes it temporarily" (labeled `memory_leak`) — fail
in **every** dense-only configuration of our 27-config sweep, including
BGE-small (a model specifically tuned for semantic retrieval). The
ceiling is the dense paradigm itself, not the embedding choice.

Hybrid retrieval is the textbook fix: BM25 anchors on shared lexical
units (rare words, technical terms, error codes) while dense embeddings
catch paraphrases. Either signal alone misses Q07-class queries; their
union catches them.

Returned rows have the same shape as `rag.retriever.retrieve_docs`, so
this module is a drop-in replacement (with one extra `fusion_score` key).
"""
from __future__ import annotations

import re
from threading import Lock
from typing import Optional

from rag.vectorstore import get_collection
from rag.retriever import retrieve_docs as _dense_retrieve

try:
    from rank_bm25 import BM25Okapi
except ImportError as exc:
    raise ImportError(
        "rank_bm25 is required for hybrid retrieval. "
        "Install with: pip install rank_bm25"
    ) from exc


_BM25_CACHE: Optional[dict] = None
_BM25_LOCK = Lock()

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    """Lowercased alphanumeric tokeniser — same form for index and queries."""
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _build_bm25() -> dict:
    """Build (and cache) the BM25 index over every chunk in ChromaDB."""
    global _BM25_CACHE
    with _BM25_LOCK:
        coll = get_collection()
        data = coll.get(include=["documents", "metadatas"])
        ids: list[str] = data["ids"]
        cache_key = (len(ids), hash(tuple(ids)))
        if _BM25_CACHE and _BM25_CACHE.get("key") == cache_key:
            return _BM25_CACHE
        documents: list[str] = data["documents"]
        metadatas: list[dict] = data["metadatas"]
        tokenised = [_tokenize(c) for c in documents]
        if not tokenised:
            raise RuntimeError(
                "ChromaDB collection is empty — call setup_vectorstore() before "
                "building the BM25 index."
            )
        bm25 = BM25Okapi(tokenised)
        _BM25_CACHE = {
            "key": cache_key,
            "bm25": bm25,
            "ids": ids,
            "documents": documents,
            "metadatas": metadatas,
        }
        return _BM25_CACHE


def hybrid_retrieve(
    query: str,
    alert_type: str = "",
    top_k: int = 3,
    fusion_k: int = 60,
    pool: Optional[int] = None,
) -> list[dict]:
    """
    Reciprocal Rank Fusion of dense + BM25 retrievers.

    Args:
        query:      Free-text alert query.
        alert_type: Classified alert type (passed to the dense retriever).
        top_k:      Number of fused results to return.
        fusion_k:   RRF constant. 60 is the industry-standard default
                    (Cormack et al., 2009); larger k flattens the curve.
        pool:       Per-leg candidate pool depth — only the top `pool`
                    ranks from each leg participate in RRF. Defaults to
                    4×top_k (min 20).

    Returns:
        List of dicts with the same fields as `retrieve_docs` plus a
        `fusion_score` (the RRF total). Every returned chunk has a real
        cosine `score` — BM25-only hits are backfilled from the full
        dense ranking so Maven's confidence math stays honest.
    """
    pool = pool or max(top_k * 4, 20)

    cache = _build_bm25()
    bm25 = cache["bm25"]
    ids = cache["ids"]
    n_chunks = len(ids)

    # Pull cosine for every chunk in one query. With ~80 chunks this is
    # essentially free, and it means BM25-only hits get a real cosine
    # score in the output (not the 0.0 placeholder that the previous
    # implementation surfaced). The fusion ranks themselves still cap at
    # the top `pool` per leg, so the RRF math is unchanged.
    dense_full = _dense_retrieve(query=query, alert_type=alert_type, top_k=n_chunks)
    by_id_full: dict[str, dict] = {d["doc_id"]: d for d in dense_full}
    dense_rank: dict[str, int] = {
        d["doc_id"]: rank for rank, d in enumerate(dense_full[:pool])
    }

    bm25_scores = bm25.get_scores(_tokenize(query))
    if bm25_scores.size == 0 or not bool(bm25_scores.any()):
        # Query had no tokens that appear in any chunk. Skip BM25 cleanly
        # rather than letting RRF silently inject a uniform rank for every
        # doc (which would dilute the dense signal).
        bm25_rank: dict[str, int] = {}
    else:
        order = sorted(range(n_chunks), key=lambda i: bm25_scores[i], reverse=True)[:pool]
        bm25_rank = {ids[i]: rank for rank, i in enumerate(order)}

    fused: dict[str, float] = {}
    for doc_id, rank in dense_rank.items():
        fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (fusion_k + rank)
    for doc_id, rank in bm25_rank.items():
        fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (fusion_k + rank)

    if not fused:
        return []

    sorted_ids = sorted(fused.keys(), key=lambda d: fused[d], reverse=True)[:top_k]
    out: list[dict] = []
    for doc_id in sorted_ids:
        # by_id_full has every chunk because dense_full pulled the whole
        # collection above — no fabricated 0.0 cosine for BM25-only hits.
        d = dict(by_id_full[doc_id])
        d["fusion_score"] = round(fused[doc_id], 6)
        out.append(d)
    return out


def query_rewrite_hybrid_retrieve(
    query: str,
    alert_type: str = "",
    top_k: int = 3,
    fusion_k: int = 60,
    pool: Optional[int] = None,
) -> list[dict]:
    """
    Hybrid retrieval with LLM-based query rewriting.

    Calls `rewrite_query` to expand the input into keyword-rich form,
    then runs the standard hybrid pipeline. Same return shape as
    `hybrid_retrieve`. Costs one Groq call per *unique* query (cached).
    """
    # Lazy import — eval-only path; no LLM dependency for default hybrid.
    from rag.query_rewriter import rewrite_query

    expanded = rewrite_query(query)
    return hybrid_retrieve(
        query=expanded,
        alert_type=alert_type,
        top_k=top_k,
        fusion_k=fusion_k,
        pool=pool,
    )
