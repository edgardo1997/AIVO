"""Persistent plugin registry backed by SQLite (plugins.db).

Stores the operational state of every plugin: identity, status, granted
permissions, install/last-execution timestamps and the trust score used to
compute a plugin's certification level.
"""

from __future__ import annotations

import os
import sqlite3
import time as time_mod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plugins (
  plugin_id   TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  version     TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'installed',
  permissions TEXT NOT NULL DEFAULT '[]',
  install_date   REAL NOT NULL,
  last_execution REAL,
  trust_score    REAL NOT NULL DEFAULT 0,
  certification  TEXT NOT NULL DEFAULT 'community',
  failure_count  INTEGER NOT NULL DEFAULT 0,
  approval_status TEXT NOT NULL DEFAULT 'pending',
  path          TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS plugin_metrics (
  plugin_id   TEXT NOT NULL,
  ts          REAL NOT NULL,
  event       TEXT NOT NULL,
  duration_ms REAL NOT NULL DEFAULT 0,
  ok          INTEGER NOT NULL DEFAULT 1,
  detail      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_plugin_metrics_id ON plugin_metrics (plugin_id);
"""


@dataclass
class PluginRecord:
    plugin_id: str
    name: str
    version: str = "1.0.0"
    status: str = "installed"
    permissions: List[str] = field(default_factory=list)
    install_date: float = field(default_factory=lambda: time_mod.time())
    last_execution: Optional[float] = None
    trust_score: float = 0.0
    certification: str = "community"
    failure_count: int = 0
    approval_status: str = "pending"
    path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "status": self.status,
            "permissions": list(self.permissions),
            "install_date": self.install_date,
            "last_execution": self.last_execution,
            "trust_score": self.trust_score,
            "certification": self.certification,
            "failure_count": self.failure_count,
            "approval_status": self.approval_status,
            "path": self.path,
        }


def _default_db_path() -> str:
    base = os.environ.get("SENTINEL_PLUGIN_DIR", "")
    if base:
        return os.path.join(base, "plugins.db")
    return os.path.join(os.path.expanduser("~/.aivo"), "plugins.db")


class PluginRegistry:
    """SQLite registry for plugin operational records."""

    def __init__(self, db_path: Optional[str] = None, clock=None) -> None:
        self._db_path = db_path or _default_db_path()
        self._clock = clock or time_mod.time
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._bootstrap()

    def _bootstrap(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    # --- records ---

    def upsert(self, record: PluginRecord) -> PluginRecord:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO plugins
                  (plugin_id, name, version, status, permissions, install_date,
                   last_execution, trust_score, certification, failure_count,
                   approval_status, path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plugin_id) DO UPDATE SET
                  name=excluded.name, version=excluded.version, status=excluded.status,
                  permissions=excluded.permissions, last_execution=excluded.last_execution,
                  trust_score=excluded.trust_score, certification=excluded.certification,
                  failure_count=excluded.failure_count, approval_status=excluded.approval_status,
                  path=excluded.path
                """,
                (
                    record.plugin_id,
                    record.name,
                    record.version,
                    record.status,
                    _encode(record.permissions),
                    record.install_date,
                    record.last_execution,
                    record.trust_score,
                    record.certification,
                    record.failure_count,
                    record.approval_status,
                    record.path,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return record

    def get(self, plugin_id: str) -> Optional[PluginRecord]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM plugins WHERE plugin_id = ?", (plugin_id,)).fetchone()
        finally:
            conn.close()
        return _row_to_record(row) if row else None

    def list(self) -> List[PluginRecord]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM plugins ORDER BY name ASC").fetchall()
        finally:
            conn.close()
        return [_row_to_record(row) for row in rows]

    def remove(self, plugin_id: str) -> bool:
        conn = self._connect()
        try:
            cursor = conn.execute("DELETE FROM plugins WHERE plugin_id = ?", (plugin_id,))
            conn.execute("DELETE FROM plugin_metrics WHERE plugin_id = ?", (plugin_id,))
            conn.commit()
        finally:
            conn.close()
        return cursor.rowcount > 0

    def update_status(self, plugin_id: str, status: str) -> None:
        conn = self._connect()
        try:
            conn.execute("UPDATE plugins SET status = ? WHERE plugin_id = ?", (status, plugin_id))
            conn.commit()
        finally:
            conn.close()

    def touch_execution(self, plugin_id: str, ok: bool, duration_ms: float = 0.0, detail: str = "") -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE plugins SET last_execution = ?, failure_count = failure_count + ? WHERE plugin_id = ?",
                (self._clock(), 0 if ok else 1, plugin_id),
            )
            conn.execute(
                "INSERT INTO plugin_metrics (plugin_id, ts, event, duration_ms, ok, detail) VALUES (?, ?, ?, ?, ?, ?)",
                (plugin_id, self._clock(), "execution", duration_ms, 1 if ok else 0, detail),
            )
            conn.commit()
        finally:
            conn.close()

    def set_trust(self, plugin_id: str, trust_score: float, certification: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE plugins SET trust_score = ?, certification = ? WHERE plugin_id = ?",
                (trust_score, certification, plugin_id),
            )
            conn.commit()
        finally:
            conn.close()

    def set_approval(self, plugin_id: str, approval_status: str) -> None:
        conn = self._connect()
        try:
            conn.execute("UPDATE plugins SET approval_status = ? WHERE plugin_id = ?", (approval_status, plugin_id))
            conn.commit()
        finally:
            conn.close()

    def metrics(self, plugin_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            if plugin_id:
                rows = conn.execute(
                    "SELECT * FROM plugin_metrics WHERE plugin_id = ? ORDER BY ts DESC LIMIT ?",
                    (plugin_id, limit),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM plugin_metrics ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        finally:
            conn.close()
        return [dict(row) for row in rows]

    def aggregate_metrics(self, plugin_id: str) -> Dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT COUNT(*) AS calls,
                       COALESCE(SUM(ok), 0) AS ok_count,
                       COALESCE(AVG(duration_ms), 0) AS avg_duration_ms,
                       COALESCE(SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END), 0) AS failures
                FROM plugin_metrics WHERE plugin_id = ?
                """,
                (plugin_id,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return {"calls": 0, "ok_count": 0, "avg_duration_ms": 0.0, "failures": 0}
        return dict(row)


def _encode(permissions: List[str]) -> str:
    import json

    return json.dumps(list(permissions), ensure_ascii=False)


def _row_to_record(row) -> Optional[PluginRecord]:
    if row is None:
        return None
    import json

    try:
        permissions = json.loads(row["permissions"]) if row["permissions"] else []
    except (TypeError, ValueError):
        permissions = []
    return PluginRecord(
        plugin_id=row["plugin_id"],
        name=row["name"],
        version=row["version"],
        status=row["status"],
        permissions=permissions,
        install_date=row["install_date"],
        last_execution=row["last_execution"],
        trust_score=row["trust_score"],
        certification=row["certification"],
        failure_count=row["failure_count"],
        approval_status=row["approval_status"],
        path=row["path"],
    )
