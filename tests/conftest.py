"""
Shared pytest fixtures for NEXUS-HEAL.

Two layers of tests live in this directory:

  * `test_watcher.py`, `test_storage.py` — deterministic unit tests.
    No Groq, no ChromaDB, no FastAPI server. Run in CI on every push.
  * `test_e2e.py` — end-to-end pipeline tests via FastAPI TestClient.
    Drives the real Groq API, needs the ChromaDB populated, and writes
    to a tmp SQLite alert store so the production DB is untouched.

The Groq + vectorstore fixtures are NOT autouse — they are opted into
by `test_e2e.py` via a module-level `pytestmark`. That way the
deterministic suites can run in CI without a Groq key.

The tmp-DB redirect happens at session start (autouse) so it covers any
`from api.server import ...` regardless of which test imports it first.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure project root is importable when pytest is launched from anywhere
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session", autouse=True)
def _isolate_alert_store() -> None:
    """Point AlertStore at a session-scoped tmp DB so tests never pollute
    the production ./nexus_alerts.db. Set BEFORE any test imports
    api.server (which constructs the module-level AlertStore at import).
    """
    tmp = Path(tempfile.gettempdir()) / "nexus_alerts_test.db"
    if tmp.exists():
        tmp.unlink()
    os.environ["NEXUS_DB_PATH"] = str(tmp)


@pytest.fixture(scope="session")
def populate_vectorstore() -> None:
    """Ingest the runbooks into ChromaDB once for the test session."""
    from rag.vectorstore import setup_vectorstore
    setup_vectorstore()


@pytest.fixture(scope="session")
def require_groq_key() -> None:
    """Skip e2e tests if no Groq key is configured."""
    if not os.getenv("GROQ_API_KEY"):
        pytest.skip(
            "GROQ_API_KEY not set — end-to-end tests need live Groq access. "
            "Populate .env and re-run, or run only the deterministic "
            "test_watcher.py / test_storage.py suites."
        )
