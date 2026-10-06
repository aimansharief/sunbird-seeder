"""SQLite store: the source of truth for what has been created and its status."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    kind       TEXT NOT NULL,
    key        TEXT NOT NULL,
    remote_id  TEXT,
    status     TEXT,
    data       TEXT NOT NULL DEFAULT '{}',
    error      TEXT,
    attempts   INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT,
    PRIMARY KEY (kind, key)
);
CREATE INDEX IF NOT EXISTS idx_kind_status ON entities (kind, status);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: str | Path):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        rec = dict(row)
        rec["data"] = json.loads(rec["data"] or "{}")
        return rec

    def get(self, kind: str, key: str) -> dict | None:
        cur = self.conn.execute(
            "SELECT * FROM entities WHERE kind=? AND key=?", (kind, key))
        return self._row(cur.fetchone())

    def status(self, kind: str, key: str) -> str | None:
        rec = self.get(kind, key)
        return rec["status"] if rec else None

    def upsert(self, kind: str, key: str, status: str,
               remote_id: str | None = None, data: dict | None = None) -> None:
        """Record a successful step. Merges data and clears any previous error."""
        existing = self.get(kind, key)
        merged = (existing["data"] if existing else {}) | (data or {})
        rid = remote_id or (existing["remote_id"] if existing else None)
        self.conn.execute(
            """INSERT INTO entities (kind, key, remote_id, status, data, error, updated_at)
               VALUES (?, ?, ?, ?, ?, NULL, ?)
               ON CONFLICT (kind, key) DO UPDATE SET
                 remote_id=excluded.remote_id, status=excluded.status,
                 data=excluded.data, error=NULL, updated_at=excluded.updated_at""",
            (kind, key, rid, status, json.dumps(merged), _now()))
        self.conn.commit()

    def mark_error(self, kind: str, key: str, error: str) -> None:
        """Record a failure without losing the last successful status."""
        self.conn.execute(
            """INSERT INTO entities (kind, key, error, attempts, updated_at)
               VALUES (?, ?, ?, 1, ?)
               ON CONFLICT (kind, key) DO UPDATE SET
                 error=excluded.error, attempts=entities.attempts + 1,
                 updated_at=excluded.updated_at""",
            (kind, key, error[:2000], _now()))
        self.conn.commit()

    def list(self, kind: str, status: str | None = None) -> list[dict]:
        if status is None:
            cur = self.conn.execute(
                "SELECT * FROM entities WHERE kind=? ORDER BY key", (kind,))
        else:
            cur = self.conn.execute(
                "SELECT * FROM entities WHERE kind=? AND status=? ORDER BY key",
                (kind, status))
        return [self._row(r) for r in cur.fetchall()]

    def counts(self) -> list[tuple]:
        cur = self.conn.execute(
            """SELECT kind, status, COUNT(*), SUM(error IS NOT NULL)
               FROM entities GROUP BY kind, status ORDER BY kind, status""")
        return [tuple(r) for r in cur.fetchall()]

    def errors(self, limit: int = 20) -> list[dict]:
        cur = self.conn.execute(
            """SELECT * FROM entities WHERE error IS NOT NULL
               ORDER BY updated_at DESC LIMIT ?""", (limit,))
        return [self._row(r) for r in cur.fetchall()]

    def close(self) -> None:
        self.conn.close()
