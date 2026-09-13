"""Durable record of plans, every external write, and a step-by-step trace.

The ledger is what makes execution resumable: each write has a stable key and a
status (pending -> done | failed). A crash leaves 'pending' rows; on resume the
engine asks the provider whether that write landed before trying again."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
  id TEXT PRIMARY KEY, status TEXT NOT NULL, body TEXT NOT NULL, created_at REAL, updated_at REAL
);
CREATE TABLE IF NOT EXISTS actions (
  key TEXT PRIMARY KEY, plan_id TEXT NOT NULL, seq INTEGER, kind TEXT, status TEXT,
  attempts INTEGER DEFAULT 0, result TEXT, error TEXT, updated_at REAL
);
CREATE TABLE IF NOT EXISTS trace (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, step TEXT, status TEXT,
  started_at REAL, ms INTEGER, detail TEXT
);
CREATE TABLE IF NOT EXISTS seen_messages (ts TEXT PRIMARY KEY, outcome TEXT, at REAL);
"""


class Ledger:
    def __init__(self, path: str | Path = ":memory:") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._db.executescript(SCHEMA)

    def _exec(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._db.execute(sql, args)
            self._db.commit()
            return cur.fetchall()

    # Plans
    def save_plan(self, plan_id: str, status: str, body: dict[str, Any]) -> None:
        now = time.time()
        self._exec(
            "INSERT INTO plans (id, status, body, created_at, updated_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET status=excluded.status, body=excluded.body, updated_at=excluded.updated_at",
            (plan_id, status, json.dumps(body, default=str), now, now),
        )

    def get_plan(self, plan_id: str) -> tuple[str, dict[str, Any]] | None:
        rows = self._exec("SELECT status, body FROM plans WHERE id=?", (plan_id,))
        return (rows[0]["status"], json.loads(rows[0]["body"])) if rows else None

    def set_status(self, plan_id: str, status: str) -> None:
        self._exec("UPDATE plans SET status=?, updated_at=? WHERE id=?", (status, time.time(), plan_id))

    def update_body(self, plan_id: str, **fields: Any) -> None:
        got = self.get_plan(plan_id)
        if got:
            status, body = got
            body.update(fields)
            self.save_plan(plan_id, status, body)

    def list_plans(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._exec("SELECT id, status, created_at FROM plans ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    # Actions
    def action(self, key: str) -> dict[str, Any] | None:
        rows = self._exec("SELECT * FROM actions WHERE key=?", (key,))
        return dict(rows[0]) if rows else None

    def mark(self, key: str, plan_id: str, seq: int, kind: str, status: str,
             result: Any = None, error: str | None = None, attempt: bool = False) -> None:
        self._exec(
            "INSERT INTO actions (key, plan_id, seq, kind, status, attempts, result, error, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET status=excluded.status, "
            "attempts=actions.attempts + ?, result=COALESCE(excluded.result, actions.result), "
            "error=excluded.error, updated_at=excluded.updated_at",
            (key, plan_id, seq, kind, status, 1 if attempt else 0,
             json.dumps(result) if result is not None else None, error, time.time(), 1 if attempt else 0),
        )

    def actions_for(self, plan_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self._exec("SELECT * FROM actions WHERE plan_id=? ORDER BY seq", (plan_id,))]

    # Trace
    def trace(self, run_id: str, step: str, status: str, started_at: float, detail: Any = None) -> None:
        ms = int((time.time() - started_at) * 1000)
        self._exec(
            "INSERT INTO trace (run_id, step, status, started_at, ms, detail) VALUES (?,?,?,?,?,?)",
            (run_id, step, status, started_at, ms, json.dumps(detail, default=str) if detail is not None else None),
        )

    def get_trace(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._exec("SELECT step, status, started_at, ms, detail FROM trace WHERE run_id=? ORDER BY id", (run_id,))
        out = []
        for r in rows:
            d = dict(r)
            d["detail"] = json.loads(d["detail"]) if d["detail"] else None
            out.append(d)
        return out

    # Slack messages already handled
    def seen(self, ts: str) -> bool:
        return bool(self._exec("SELECT 1 FROM seen_messages WHERE ts=?", (ts,)))

    def mark_seen(self, ts: str, outcome: str) -> None:
        self._exec("INSERT OR IGNORE INTO seen_messages (ts, outcome, at) VALUES (?,?,?)", (ts, outcome, time.time()))
