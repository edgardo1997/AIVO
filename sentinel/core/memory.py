import json
import sqlite3
import threading
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

logger = logging.getLogger(__name__)


class Memory:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = str(Path.home() / ".sentinel" / "memory.db")
        self._db_path = db_path
        self._local = threading.local()
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS snapshots (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                context TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                label TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                data TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS user_preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(timestamp);
        """)
        conn.commit()

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    def store(self, key: str, value: Any) -> None:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        serialized = json.dumps(value)
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT OR REPLACE INTO kv_store (key, value, updated_at) VALUES (?, ?, ?)",
                (key, serialized, now),
            )
            conn.commit()

    def get(self, key: str, default: Any = None) -> Any:
        conn = self._get_conn()
        row = conn.execute("SELECT value FROM kv_store WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return json.loads(row["value"])

    def delete(self, key: str) -> None:
        with self._lock:
            conn = self._get_conn()
            conn.execute("DELETE FROM kv_store WHERE key = ?", (key,))
            conn.commit()

    def list_keys(self, prefix: str = "") -> List[str]:
        conn = self._get_conn()
        if prefix:
            rows = conn.execute("SELECT key FROM kv_store WHERE key LIKE ?", (prefix + "%",)).fetchall()
        else:
            rows = conn.execute("SELECT key FROM kv_store").fetchall()
        return [r["key"] for r in rows]

    def save_snapshot(self, context_dict: Dict[str, Any]) -> str:
        sid = uuid.uuid4().hex[:12]
        ts = context_dict.get("timestamp", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
        serialized = json.dumps(context_dict)
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO snapshots (id, timestamp, context) VALUES (?, ?, ?)",
                (sid, ts, serialized),
            )
            conn.commit()
        return sid

    def get_snapshots(self, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, timestamp, context FROM snapshots ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        results = []
        for row in rows:
            entry = json.loads(row["context"])
            entry["_snapshot_id"] = row["id"]
            entry["_snapshot_timestamp"] = row["timestamp"]
            results.append(entry)
        return results

    def count_snapshots(self) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) as cnt FROM snapshots").fetchone()
        return row["cnt"] if row else 0

    def create_session(self, label: str = "") -> str:
        sid = uuid.uuid4().hex[:16]
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO sessions (id, label, created_at, updated_at, data) VALUES (?, ?, ?, ?, ?)",
                (sid, label, now, now, "{}"),
            )
            conn.commit()
        return sid

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id, label, created_at, updated_at, data FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "label": row["label"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "data": json.loads(row["data"]),
        }

    def update_session(self, session_id: str, data: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        serialized = json.dumps(data)
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "UPDATE sessions SET data = ?, updated_at = ? WHERE id = ?",
                (serialized, now, session_id),
            )
            conn.commit()

    def store_preference(self, session_id: str, key: str, value: Any) -> None:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        serialized = json.dumps(value)
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT OR REPLACE INTO user_preferences (key, value, updated_at) VALUES (?, ?, ?)",
                (f"{session_id}:{key}", serialized, now),
            )
            conn.commit()

    def get_preferences(self, session_id: str) -> Dict[str, Any]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT key, value FROM user_preferences WHERE key LIKE ?",
            (f"{session_id}:%",),
        ).fetchall()
        result = {}
        prefix = f"{session_id}:"
        for row in rows:
            k = row["key"][len(prefix):]
            try:
                result[k] = json.loads(row["value"])
            except (json.JSONDecodeError, TypeError):
                result[k] = row["value"]
        return result

    def cleanup_old_snapshots(self, keep: int = 100) -> int:
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """DELETE FROM snapshots WHERE id NOT IN (
                    SELECT id FROM snapshots ORDER BY timestamp DESC LIMIT ?
                )""",
                (keep,),
            )
            conn.commit()
            deleted = conn.total_changes
        return deleted
