"""
Shared pytest fixtures for NEXUS-HEAL end-to-end tests.

The vectorstore must be ingested exactly once per test session — the full
pipeline needs it populated before any retrieval. Skip the whole suite if
GROQ_API_KEY is missing so the test run fails loudly rather than silently
asking Groq with no auth.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure project root is importable when pytest is launched from anywhere
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session", autouse=True)
def _populate_vectorstore() -> None:
    """Ingest the 10 runbooks into ChromaDB once before any test runs."""
    from rag.vectorstore import setup_vectorstore
    setup_vectorstore()


@pytest.fixture(scope="session", autouse=True)
def _require_groq_key() -> None:
    """End-to-end tests drive real LLM calls — fail fast if the key is absent."""
    if not os.getenv("GROQ_API_KEY"):
        pytest.skip(
            "GROQ_API_KEY not set — the end-to-end smoke test needs live "
            "Groq access. Populate .env and re-run."
        )
