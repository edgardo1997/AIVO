"""Event Store — persistent pipeline history via SQLite."""

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from sentinel.core.events import SentinelEvent

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id     TEXT PRIMARY KEY,
    event_type   TEXT NOT NULL,
    component    TEXT NOT NULL DEFAULT '',
    session_id   TEXT NOT NULL,
    request_id   TEXT NOT NULL DEFAULT '',
    timestamp    REAL NOT NULL,
    status       TEXT NOT NULL DEFAULT '',
    priority     TEXT NOT NULL DEFAULT 'normal',
    progress     INTEGER,
    tool         TEXT,
    message      TEXT,
    details      TEXT,
    duration     REAL
);

CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_request ON events(request_id);
CREATE INDEX IF NOT EXISTS idx_events_type    ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_ts      ON events(timestamp);
"""


class EventStore:
    def __init__(self, db_path: Optional[str] = None):
        self._db_path = str(db_path or _default_db_path())
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    def save(self, event: SentinelEvent) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO events
                (event_id, event_type, component, session_id, request_id,
                 timestamp, status, priority, progress, tool, message,
                 details, duration)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.event_type,
                event.component,
                event.session_id,
                event.request_id,
                event.timestamp,
                event.status,
                event.priority,
                event.progress,
                event.tool,
                event.message,
                json.dumps(event.details) if event.details else None,
                event.duration,
            ),
        )
        conn.commit()

    def query(self, session_id: str) -> List[SentinelEvent]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp ASC",
            (session_id,),
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def get_timeline(self, request_id: str) -> List[SentinelEvent]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM events WHERE request_id = ? ORDER BY timestamp ASC",
            (request_id,),
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def stats(self) -> Dict[str, Any]:
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        by_type = {
            row["event_type"]: row["cnt"]
            for row in conn.execute(
                "SELECT event_type, COUNT(*) AS cnt FROM events GROUP BY event_type ORDER BY cnt DESC"
            ).fetchall()
        }
        failed = conn.execute(
            "SELECT COUNT(*) FROM events WHERE status = 'failed'"
        ).fetchone()[0]
        avg_duration = conn.execute(
            "SELECT AVG(duration) FROM events WHERE duration IS NOT NULL"
        ).fetchone()[0]
        return {
            "total_events": total,
            "by_type": by_type,
            "failed_count": failed,
            "avg_duration_ms": round(avg_duration * 1000, 2) if avg_duration else 0.0,
        }

    def _row_to_event(self, row: sqlite3.Row) -> SentinelEvent:
        return SentinelEvent(
            event_id=row["event_id"],
            event_type=row["event_type"],
            timestamp=row["timestamp"],
            session_id=row["session_id"],
            request_id=row["request_id"],
            component=row["component"],
            status=row["status"],
            priority=row["priority"],
            progress=row["progress"],
            tool=row["tool"],
            message=row["message"],
            details=json.loads(row["details"]) if row["details"] else None,
            duration=row["duration"],
        )

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None


def _default_db_path() -> str:
    data_home = Path.home() / ".sentinel"
    data_home.mkdir(parents=True, exist_ok=True)
    return str(data_home / "events.db")
