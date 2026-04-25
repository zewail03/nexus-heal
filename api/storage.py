"""
SQLite-backed alert store.

Replaces the in-memory `_pending_alerts: dict` from earlier milestones
so the Mission Control dashboard survives a server restart.

Schema (single table):

    alerts (
        alert_id    TEXT PRIMARY KEY,
        state_json  TEXT NOT NULL,
        created_at  TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
    )

Each call opens its own connection (sqlite3 connections are not safe to
share across threads, and FastAPI runs handlers from a thread pool).
WAL is enabled so concurrent readers don't block the writer during the
same request burst.

Test isolation
--------------
The default DB path is `./nexus_alerts.db`. Override via the
`NEXUS_DB_PATH` environment variable (the e2e pytest fixture points
this at a tmp file so tests never pollute the production DB).
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


DEFAULT_DB_PATH = "./nexus_alerts.db"


class AlertStore:
    """Dict-like persistent store for NexusState dicts keyed by alert_id."""

    def __init__(self, db_path: str | None = None) -> None:
        # Honour env var so tests can swap the DB without import-time gymnastics.
        self.db_path = db_path or os.getenv("NEXUS_DB_PATH", DEFAULT_DB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True) if "/" in self.db_path or "\\" in self.db_path else None
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=5.0, isolation_level=None)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id   TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS alerts_updated_idx ON alerts(updated_at DESC)"
            )

    # -- mutators --------------------------------------------------------

    def put(self, alert_id: str, state: dict) -> None:
        """Insert or replace the full state for `alert_id`."""
        payload = json.dumps(state, default=str)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO alerts (alert_id, state_json, created_at, updated_at)
                VALUES (?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(alert_id) DO UPDATE SET
                    state_json = excluded.state_json,
                    updated_at = datetime('now')
                """,
                (alert_id, payload),
            )

    def delete(self, alert_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM alerts WHERE alert_id = ?", (alert_id,))
            return cur.rowcount > 0

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM alerts")

    # -- accessors -------------------------------------------------------

    def get(self, alert_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT state_json FROM alerts WHERE alert_id = ?", (alert_id,)
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return None

    def __contains__(self, alert_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM alerts WHERE alert_id = ?", (alert_id,)
            ).fetchone()
        return row is not None

    def __len__(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]

    def all(self, *, newest_first: bool = True) -> dict[str, dict]:
        """Return every stored state keyed by alert_id."""
        order = "DESC" if newest_first else "ASC"
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT alert_id, state_json FROM alerts ORDER BY updated_at {order}"
            ).fetchall()
        out: dict[str, dict] = {}
        for alert_id, payload in rows:
            try:
                out[alert_id] = json.loads(payload)
            except json.JSONDecodeError:
                continue
        return out
