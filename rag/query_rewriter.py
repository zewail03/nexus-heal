"""
LLM-based query rewriting for retrieval.

Q07/Q03-class queries — fully paraphrased, with zero domain vocabulary —
miss in both dense and hybrid retrieval (confirmed by 27-config sweep
+ hybrid eval). The paradigm-level fix is to rewrite the query into
keyword form *before* retrieval, surfacing the technical terms that
runbooks actually contain.

Example
-------
Input:  "Service becomes unresponsive after running for a day,
         a manual restart fixes it temporarily"
Output: "Service becomes unresponsive after running for a day,
         a manual restart fixes it temporarily memory_leak OOM heap
         RSS swap GC long uptime restart workaround"

Both the original query and the LLM expansion are concatenated so the
dense leg keeps its paraphrase-friendliness while BM25 gets the
keyword anchors it needs.
"""
from __future__ import annotations

from threading import Lock
from typing import Optional

from langchain_groq import ChatGroq

from config import GROQ_API_KEY, LLM_MODEL


_REWRITE_CACHE: dict[str, str] = {}
_CACHE_LOCK = Lock()
_LLM_SINGLETON: Optional[ChatGroq] = None


# Hand-curated vocabulary scoped to the 26-runbook KB. Listed explicitly
# so the rewriter cannot wander into off-topic SRE jargon (e.g. AWS
# service names that don't appear in our runbooks).
_DOMAIN_VOCABULARY = """
ALERT TYPES: cpu_spike, memory_leak, disk_full, db_connection,
network_latency, ssl_expired, api_timeout, pod_crash, queue_overflow,
auth_failure, dns_failure, rate_limit_exceeded, deadlock, clock_drift,
kafka_lag, iops_throttle, cert_chain, secrets_rotation,
websocket_disconnect_storm, cdn_cache_miss, image_pull_backoff,
node_pressure_eviction, cache_invalidation, circuit_breaker,
log_pipeline_lag, replication_lag.

TECHNICAL TERMS: OOM, OOMKilled, heap, RSS, swap, GC, JVM,
CrashLoopBackOff, ImagePullBackOff, readiness probe, liveness probe,
exit code 137, exit code 139, SIGKILL, kubectl, systemctl, df, du,
iostat, netstat, dig, nslookup, openssl, certificate, x509,
pg_isready, pg_stat_activity, replication slot, WAL, deadlock,
Kafka consumer lag, partition, offset, throughput, latency, p99,
TLS handshake, SNI, SAN, root CA, expired, revoked, RBAC, IAM,
secret, vault, token rotation, NXDOMAIN, SERVFAIL, resolver, upstream,
HTTP 429, 502, 503, 504, throttle, backoff, eviction, taint, pressure.
"""


_REWRITE_PROMPT = """You are an SRE keyword expander. Given a colloquial
incident description, output technical keywords and synonyms that would
appear in a runbook for this kind of incident.

Domain vocabulary (only expand into terms relevant to these):
{vocab}

Rules:
- Output ONLY a single line of space-separated technical keywords.
- Pick the alert type(s) that best match (e.g. memory_leak, cpu_spike).
- Include relevant error codes, command names, and exact technical terms.
- Do NOT repeat the input description — only output expansion keywords.
- 5-15 tokens, no sentences, no markdown, no explanations.

Description: "{query}"
Keywords:"""


def _get_llm() -> ChatGroq:
    global _LLM_SINGLETON
    if _LLM_SINGLETON is None:
        _LLM_SINGLETON = ChatGroq(
            model=LLM_MODEL,
            temperature=0.0,  # deterministic — eval reproducibility
            api_key=GROQ_API_KEY,
        )
    return _LLM_SINGLETON


def rewrite_query(query: str) -> str:
    """
    Return `query` augmented with an LLM-generated keyword expansion.

    The original query is preserved (not replaced) so the dense leg
    keeps its paraphrase signal; the expansion gives BM25 anchors it
    would otherwise miss. In-process cached so repeated calls (eval
    re-runs, Maven retries) cost zero tokens.
    """
    with _CACHE_LOCK:
        if query in _REWRITE_CACHE:
            return _REWRITE_CACHE[query]

    prompt = _REWRITE_PROMPT.format(
        vocab=_DOMAIN_VOCABULARY.strip(),
        query=query,
    )
    response = _get_llm().invoke(prompt)
    expansion = (response.content or "").strip()
    # Strip code fences / explanations; keep first non-empty line.
    if expansion.startswith("```"):
        expansion = expansion.split("\n", 1)[1] if "\n" in expansion else ""
        if expansion.endswith("```"):
            expansion = expansion[:-3]
    expansion = expansion.split("\n", 1)[0].strip()

    # Defensive: an empty expansion = degenerate to plain query rather
    # than feed the retriever something weirder than it had before.
    combined = f"{query} {expansion}".strip() if expansion else query

    with _CACHE_LOCK:
        _REWRITE_CACHE[query] = combined
    return combined
