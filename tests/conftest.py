"""
Shared pytest fixtures for NEXUS-HEAL.

Two layers of tests live in this directory:

  * `test_watcher.py` — deterministic unit tests for the Watcher
    safety allowlist + subprocess pass. No Groq, no ChromaDB. Runs
    in CI on every push.
  * `test_e2e.py` — end-to-end pipeline tests via FastAPI TestClient.
    Drives the real Groq API and needs the ChromaDB populated.

The fixtures below are NOT autouse — they are explicitly opted into
by `test_e2e.py` via a module-level `pytestmark`. That way the Watcher
tests can run in CI without a Groq key, and the heavyweight setup only
happens for tests that actually need it.
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


@pytest.fixture(scope="session")
def populate_vectorstore() -> None:
    """Ingest the 10 runbooks into ChromaDB once for the test session."""
    from rag.vectorstore import setup_vectorstore
    setup_vectorstore()


@pytest.fixture(scope="session")
def require_groq_key() -> None:
    """Skip e2e tests if no Groq key is configured."""
    if not os.getenv("GROQ_API_KEY"):
        pytest.skip(
            "GROQ_API_KEY not set — end-to-end tests need live Groq access. "
            "Populate .env and re-run, or run only the deterministic "
            "Watcher tests with `pytest tests/test_watcher.py`."
        )
