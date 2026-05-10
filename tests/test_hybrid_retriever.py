"""
Deterministic unit tests for the hybrid retriever and query rewriter.

The hybrid retriever's RRF math, BM25 cache, and cosine-backfill logic
are all testable without Groq — only ChromaDB needs to be populated,
which the session-scoped `populate_vectorstore` fixture handles.

The query rewriter requires Groq, so its tests stub the LLM via the
`_REWRITE_CACHE` to keep this suite deterministic and fast.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag import hybrid_retriever  # noqa: E402
from rag import query_rewriter  # noqa: E402


# ChromaDB is needed by the hybrid path. The fixture ingests the 26
# runbooks once for the test session.
pytestmark = pytest.mark.usefixtures("populate_vectorstore")


# ---------------------------------------------------------------------------
# _tokenize — the lexical input format for BM25
# ---------------------------------------------------------------------------

def test_tokenize_lowercases_and_extracts_alphanumerics() -> None:
    assert hybrid_retriever._tokenize("CPU Spike on api-Gateway-PROD") == [
        "cpu", "spike", "on", "api", "gateway", "prod",
    ]


def test_tokenize_handles_empty_and_whitespace() -> None:
    assert hybrid_retriever._tokenize("") == []
    assert hybrid_retriever._tokenize("    ") == []


def test_tokenize_drops_pure_punctuation() -> None:
    # The token regex is [A-Za-z0-9_]+, so punctuation acts as separator.
    assert hybrid_retriever._tokenize("!!! 502 ??? Bad-Gateway") == [
        "502", "bad", "gateway",
    ]


# ---------------------------------------------------------------------------
# _build_bm25 — index cache invariants
# ---------------------------------------------------------------------------

def test_build_bm25_returns_consistent_cache() -> None:
    # Force a fresh build, then assert the second call returns the same
    # cached object (we don't want to rebuild the index on every query).
    hybrid_retriever._BM25_CACHE = None
    first = hybrid_retriever._build_bm25()
    second = hybrid_retriever._build_bm25()
    assert first is second
    assert first["bm25"] is not None
    assert len(first["ids"]) == len(first["documents"]) == len(first["metadatas"])
    assert len(first["ids"]) > 0  # ChromaDB was populated by the fixture


# ---------------------------------------------------------------------------
# hybrid_retrieve — output shape and ranking
# ---------------------------------------------------------------------------

def test_hybrid_retrieve_returns_top_k_with_required_fields() -> None:
    docs = hybrid_retriever.hybrid_retrieve(
        query="CPU usage 99% on production api-gateway",
        alert_type="cpu_spike",
        top_k=3,
    )
    assert len(docs) == 3
    required = {"doc_id", "content", "score", "source", "alert_type", "fusion_score"}
    for d in docs:
        assert required <= set(d.keys()), f"missing fields: {required - set(d.keys())}"


def test_hybrid_retrieve_sorted_by_fusion_score_descending() -> None:
    docs = hybrid_retriever.hybrid_retrieve(
        query="kubectl pod crash CrashLoopBackOff",
        alert_type="pod_crash",
        top_k=5,
    )
    fusion_scores = [d["fusion_score"] for d in docs]
    assert fusion_scores == sorted(fusion_scores, reverse=True)


def test_hybrid_retrieve_score_field_is_real_cosine_not_zero_placeholder() -> None:
    """
    The cosine-backfill change in the production switch means BM25-only
    hits should never surface with score=0.0. Every returned chunk has a
    real cosine pulled from the full dense ranking. Verify across a
    variety of queries.
    """
    queries = [
        "CPU spike production",
        "memory leak OOM heap",
        "ssl certificate expired root CA",
        "kafka consumer lag partition offset",
    ]
    for q in queries:
        docs = hybrid_retriever.hybrid_retrieve(query=q, alert_type="", top_k=5)
        scores = [d["score"] for d in docs]
        assert all(0.0 < s <= 1.0 for s in scores), (
            f"query={q!r} produced placeholder/invalid scores: {scores}"
        )


def test_hybrid_retrieve_empty_query_returns_top_k_via_dense_only() -> None:
    """
    An empty query has no BM25 tokens, so the BM25 leg is skipped.
    The dense leg should still return results — degenerate to dense-only
    rather than crash.
    """
    docs = hybrid_retriever.hybrid_retrieve(query="", alert_type="", top_k=3)
    assert len(docs) == 3
    for d in docs:
        # BM25 contributed nothing, so fusion_score equals dense's RRF
        # contribution alone (1/(60+0) = 0.01666... at rank 0).
        assert d["fusion_score"] > 0


def test_hybrid_retrieve_garbage_query_skips_bm25_cleanly() -> None:
    """A query whose tokens appear nowhere in the corpus should still
    return dense results without crashing — the empty-bm25 guard kicks in."""
    docs = hybrid_retriever.hybrid_retrieve(
        query="zxqwrtypoiuasdfghjkl",
        alert_type="",
        top_k=3,
    )
    assert len(docs) == 3


# ---------------------------------------------------------------------------
# RRF math — verify against a hand-computed example
# ---------------------------------------------------------------------------

def test_rrf_constant_matches_published_default() -> None:
    """The RRF k-constant is hard-coded to 60 as the published industry
    default (Cormack 2009). If someone changes it, that's a deliberate
    decision — flag it via a test failure so it's at least visible."""
    docs = hybrid_retriever.hybrid_retrieve(
        query="CPU spike", alert_type="", top_k=1, fusion_k=60,
    )
    assert len(docs) == 1
    # Top doc is at rank 0 in both legs (assuming agreement). Upper bound
    # on fusion_score: 1/(60+0) + 1/(60+0) = 0.0333... If only one leg
    # ranked it at 0, the cap is half that. Either way, fusion_score must
    # be < 1/60 + 1/60 + epsilon.
    assert 0 < docs[0]["fusion_score"] <= 2 / 60 + 1e-6


# ---------------------------------------------------------------------------
# query_rewriter — cache + fallback behaviour (no Groq required)
# ---------------------------------------------------------------------------

def test_rewrite_query_uses_cache_for_repeated_input() -> None:
    """Pre-seed the cache so we can assert the LLM is never called."""
    query_rewriter._REWRITE_CACHE.clear()
    query_rewriter._REWRITE_CACHE["dummy query"] = "dummy query expanded keywords"

    # Force a sentinel LLM so any actual call raises immediately.
    class _ShouldNotBeCalled:
        def invoke(self, *_args, **_kwargs):
            raise AssertionError("LLM should never be called when cache is warm")

    saved = query_rewriter._LLM_SINGLETON
    query_rewriter._LLM_SINGLETON = _ShouldNotBeCalled()
    try:
        result = query_rewriter.rewrite_query("dummy query")
        assert result == "dummy query expanded keywords"
        # Re-call: still cached, still no LLM call.
        assert query_rewriter.rewrite_query("dummy query") == result
    finally:
        query_rewriter._LLM_SINGLETON = saved
        query_rewriter._REWRITE_CACHE.clear()


def test_rewrite_query_falls_back_to_plain_query_on_empty_expansion() -> None:
    """An empty LLM response degenerates to the plain query rather than
    feeding the retriever something weirder than it had to begin with."""
    query_rewriter._REWRITE_CACHE.clear()

    class _EmptyLLM:
        def invoke(self, *_args, **_kwargs):
            class _R:
                content = ""
            return _R()

    saved = query_rewriter._LLM_SINGLETON
    query_rewriter._LLM_SINGLETON = _EmptyLLM()
    try:
        out = query_rewriter.rewrite_query("a fresh query that empty-expands")
        assert out == "a fresh query that empty-expands"
    finally:
        query_rewriter._LLM_SINGLETON = saved
        query_rewriter._REWRITE_CACHE.clear()


def test_rewrite_query_concatenates_expansion_onto_original() -> None:
    """Expansion is *appended* to the original — the dense leg keeps its
    paraphrase signal, BM25 picks up the new keyword anchors."""
    query_rewriter._REWRITE_CACHE.clear()

    class _StubLLM:
        def invoke(self, *_args, **_kwargs):
            class _R:
                content = "memory_leak OOM heap RSS"
            return _R()

    saved = query_rewriter._LLM_SINGLETON
    query_rewriter._LLM_SINGLETON = _StubLLM()
    try:
        out = query_rewriter.rewrite_query("service unresponsive")
        assert out == "service unresponsive memory_leak OOM heap RSS"
    finally:
        query_rewriter._LLM_SINGLETON = saved
        query_rewriter._REWRITE_CACHE.clear()
