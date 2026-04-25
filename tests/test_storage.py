"""
Tests for the SQLite-backed AlertStore (api/storage.py).

Pure unit tests — no Groq, no ChromaDB, no FastAPI server.  Each test
gets its own tmp DB via pytest's `tmp_path`, so the production
`./nexus_alerts.db` is never touched.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.storage import AlertStore  # noqa: E402


@pytest.fixture
def store(tmp_path: Path) -> AlertStore:
    return AlertStore(db_path=str(tmp_path / "alerts_test.db"))


def _state(alert_id: str, **extra) -> dict:
    base = {
        "alert_id": alert_id,
        "alert_raw": "test alert",
        "alert_type": "cpu_spike",
        "alert_severity": "HIGH",
        "diagnosis": "test diagnosis",
        "fix_plan": ["step 1"],
        "fix_commands": ["df -h"],
        "command_results": [],
        "execution_status": "pending",
        "iteration_count": 1,
    }
    base.update(extra)
    return base


def test_put_get_round_trip(store: AlertStore) -> None:
    state = _state("A-001", diagnosis="cpu pegged")
    store.put("A-001", state)
    got = store.get("A-001")
    assert got is not None
    assert got["alert_id"] == "A-001"
    assert got["diagnosis"] == "cpu pegged"
    assert got["fix_plan"] == ["step 1"]


def test_get_missing_returns_none(store: AlertStore) -> None:
    assert store.get("does-not-exist") is None


def test_contains(store: AlertStore) -> None:
    store.put("A-001", _state("A-001"))
    assert "A-001" in store
    assert "A-999" not in store


def test_len(store: AlertStore) -> None:
    assert len(store) == 0
    store.put("A-001", _state("A-001"))
    store.put("A-002", _state("A-002"))
    assert len(store) == 2


def test_put_overwrites(store: AlertStore) -> None:
    store.put("A-001", _state("A-001", diagnosis="first"))
    store.put("A-001", _state("A-001", diagnosis="second"))
    assert len(store) == 1
    assert store.get("A-001")["diagnosis"] == "second"


def test_all_returns_every_state(store: AlertStore) -> None:
    for i in range(5):
        store.put(f"A-{i:03d}", _state(f"A-{i:03d}"))
    everything = store.all()
    assert set(everything.keys()) == {f"A-{i:03d}" for i in range(5)}
    assert all(v["alert_id"].startswith("A-") for v in everything.values())


def test_delete(store: AlertStore) -> None:
    store.put("A-001", _state("A-001"))
    assert store.delete("A-001") is True
    assert "A-001" not in store
    # Deleting again returns False
    assert store.delete("A-001") is False


def test_clear(store: AlertStore) -> None:
    for i in range(3):
        store.put(f"A-{i}", _state(f"A-{i}"))
    assert len(store) == 3
    store.clear()
    assert len(store) == 0


def test_persists_across_instances(tmp_path: Path) -> None:
    """Survives 'restart' — write with one instance, read with a fresh one
    pointing at the same file."""
    db = str(tmp_path / "persist.db")
    s1 = AlertStore(db_path=db)
    s1.put("A-001", _state("A-001", diagnosis="durable"))
    del s1

    s2 = AlertStore(db_path=db)
    assert "A-001" in s2
    assert s2.get("A-001")["diagnosis"] == "durable"


def test_nested_lists_and_dicts_round_trip(store: AlertStore) -> None:
    """The Watcher's command_results are list-of-dicts; make sure they
    survive JSON round-trip."""
    state = _state("A-001", command_results=[
        {"command": "df -h", "executed": True, "exit_code": 0,
         "stdout": "Filesystem  Size  Used", "classification": "safe"},
        {"command": "rm -rf /tmp", "executed": False,
         "classification": "mutation", "error": "manual review required"},
    ])
    store.put("A-001", state)
    got = store.get("A-001")
    assert len(got["command_results"]) == 2
    assert got["command_results"][0]["executed"] is True
    assert got["command_results"][1]["classification"] == "mutation"


def test_env_var_overrides_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """If db_path is None, the constructor falls back to NEXUS_DB_PATH."""
    target = tmp_path / "from_env.db"
    monkeypatch.setenv("NEXUS_DB_PATH", str(target))
    s = AlertStore()
    s.put("A-001", _state("A-001"))
    assert target.exists()
    assert "A-001" in s


def test_all_orders_newest_first(store: AlertStore) -> None:
    import time
    store.put("A-001", _state("A-001"))
    time.sleep(1.1)  # SQLite datetime() granularity is 1 second
    store.put("A-002", _state("A-002"))
    keys = list(store.all(newest_first=True).keys())
    # A-002 was inserted later, must come first
    assert keys[0] == "A-002"
    assert keys[1] == "A-001"
