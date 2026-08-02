"""Product-level metrics for Sentinel Desktop.

Tracks the numbers that describe whether the product *works for the user*:
time to first action, completed actions, UX errors, automations created,
usage by mode and daily retention. Data lives in a small dedicated SQLite
database so it never touches the governed runtime schema.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

EVENT_FIRST_ACTION = "first_action"
EVENT_ACTION_COMPLETED = "action_completed"
EVENT_UX_ERROR = "ux_error"
EVENT_AUTOMATION_CREATED = "automation_created"
EVENT_MODE_USED = "mode_used"
EVENT_SESSION = "session"
EVENT_COMMAND = "command"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS product_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  event_type TEXT NOT NULL,
  details TEXT
);
CREATE TABLE IF NOT EXISTS product_first_actions (
  session_id TEXT PRIMARY KEY,
  recorded_at TEXT NOT NULL,
  tool_id TEXT NOT NULL DEFAULT '',
  latency_ms REAL
);
CREATE TABLE IF NOT EXISTS product_daily (
  day TEXT PRIMARY KEY,
  actions_completed INTEGER NOT NULL DEFAULT 0,
  automations_created INTEGER NOT NULL DEFAULT 0,
  ux_errors INTEGER NOT NULL DEFAULT 0,
  first_actions INTEGER NOT NULL DEFAULT 0,
  sessions INTEGER NOT NULL DEFAULT 0,
  mode_uses TEXT NOT NULL DEFAULT '{}'
);
"""


def _default_db_path() -> str:
    base = os.environ.get("SENTINEL_PRODUCT_DIR", "")
    if base:
        return os.path.join(base, "product_metrics.db")
    try:
        from windows_acl import sentinel_storage_paths

        root = sentinel_storage_paths().get("sentinel_config")
    except Exception:
        root = os.path.expanduser("~/.sentinel")
    if not root:
        root = os.path.expanduser("~/.sentinel")
    return os.path.join(str(root), "product", "product_metrics.db")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _day_key(ts: Optional[float] = None) -> str:
    instant = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else _utc_now()
    return instant.strftime("%Y-%m-%d")


class ProductMetricsService:
    """Record and aggregate product metrics.

    ``db_path`` and ``clock`` are injectable so unit tests stay hermetic and
    deterministic without touching user data.
    """

    def __init__(self, db_path: Optional[str] = None, clock=None) -> None:
        self._db_path = db_path or _default_db_path()
        self._clock = clock or (lambda: time_import().time())
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._bootstrap()

    # --- storage ---

    def _bootstrap(self) -> None:
        with self._lock:
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

    def _now_iso(self) -> str:
        return datetime.fromtimestamp(self._clock(), tz=timezone.utc).isoformat()

    # --- record ---

    def record(self, event_type: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not event_type:
            return {"success": False, "error": "event_type required"}
        details = details or {}
        ts = self._clock()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO product_events (ts, event_type, details) VALUES (?, ?, ?)",
                    (self._now_iso(), event_type, json.dumps(details, ensure_ascii=False)),
                )
                self._increment_daily(conn, event_type, details, ts)
                conn.commit()
            finally:
                conn.close()
        return {"success": True, "event_type": event_type}

    def record_first_action_once(self, session_id: str, details: Optional[Dict[str, Any]] = None) -> bool:
        """Atomically record the first governed success for one authenticated session.

        The database, rather than a process-local flag, is the authority. This
        remains correct when the sidecar restarts and when two executions race.
        """
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            return False
        event_details = dict(details or {})
        event_details["session_id"] = normalized_session_id
        ts = self._clock()
        with self._lock:
            conn = self._connect()
            try:
                inserted = conn.execute(
                    """INSERT OR IGNORE INTO product_first_actions
                       (session_id, recorded_at, tool_id, latency_ms) VALUES (?, ?, ?, ?)""",
                    (
                        normalized_session_id,
                        self._now_iso(),
                        str(event_details.get("tool_id", "")),
                        event_details.get("latency_ms"),
                    ),
                ).rowcount
                if not inserted:
                    conn.rollback()
                    return False
                conn.execute(
                    "INSERT INTO product_events (ts, event_type, details) VALUES (?, ?, ?)",
                    (self._now_iso(), EVENT_FIRST_ACTION, json.dumps(event_details, ensure_ascii=False)),
                )
                self._increment_daily(conn, EVENT_FIRST_ACTION, event_details, ts)
                conn.commit()
                return True
            finally:
                conn.close()

    def _increment_daily(self, conn: sqlite3.Connection, event_type: str, details: Dict[str, Any], ts: float) -> None:
        day = _day_key(ts)
        conn.execute(
            "INSERT OR IGNORE INTO product_daily (day) VALUES (?)",
            (day,),
        )
        column = {
            EVENT_FIRST_ACTION: "first_actions",
            EVENT_ACTION_COMPLETED: "actions_completed",
            EVENT_UX_ERROR: "ux_errors",
            EVENT_AUTOMATION_CREATED: "automations_created",
            EVENT_SESSION: "sessions",
        }.get(event_type)
        if column:
            conn.execute(f"UPDATE product_daily SET {column} = {column} + 1 WHERE day = ?", (day,))
        if event_type == EVENT_MODE_USED:
            mode = str(details.get("mode", "unknown"))
            row = conn.execute("SELECT mode_uses FROM product_daily WHERE day = ?", (day,)).fetchone()
            uses = {}
            if row and row["mode_uses"]:
                try:
                    uses = json.loads(row["mode_uses"])
                except (TypeError, ValueError):
                    uses = {}
            uses[mode] = uses.get(mode, 0) + 1
            conn.execute("UPDATE product_daily SET mode_uses = ? WHERE day = ?", (json.dumps(uses), day))

    # --- aggregate ---

    def overview(self, days: int = 14) -> Dict[str, Any]:
        span = max(days, 1)
        cutoff = _day_key(self._clock() - span * 86400)
        with self._lock:
            conn = self._connect()
            try:
                totals = conn.execute(
                    """
                    SELECT COALESCE(SUM(actions_completed), 0)  AS actions_completed,
                           COALESCE(SUM(automations_created), 0) AS automations_created,
                           COALESCE(SUM(ux_errors), 0)          AS ux_errors,
                           COALESCE(SUM(first_actions), 0)      AS first_actions,
                           COALESCE(SUM(sessions), 0)           AS sessions,
                           COUNT(*)                             AS active_days
                    FROM product_daily WHERE day >= ?
                    """,
                    (cutoff,),
                ).fetchone()
                daily_rows = conn.execute(
                    "SELECT * FROM product_daily WHERE day >= ? ORDER BY day ASC", (cutoff,)
                ).fetchall()
                mode_rows = conn.execute(
                    "SELECT details FROM product_events WHERE event_type = ? AND ts >= ?",
                    (EVENT_MODE_USED, datetime.fromtimestamp(self._clock() - span * 86400, tz=timezone.utc).isoformat()),
                ).fetchall()
            finally:
                conn.close()

        mode_uses: Dict[str, int] = {}
        for row in mode_rows:
            try:
                details = json.loads(row["details"])
            except (TypeError, ValueError):
                details = {}
            mode = str(details.get("mode", "unknown"))
            mode_uses[mode] = mode_uses.get(mode, 0) + 1

        actions_completed = int(totals["actions_completed"] or 0)
        sessions = int(totals["sessions"] or 0)
        first_actions = int(totals["first_actions"] or 0)
        automations = int(totals["automations_created"] or 0)
        ux_errors = int(totals["ux_errors"] or 0)
        active_days = int(totals["active_days"] or 0)

        return {
            "span_days": span,
            "time_to_first_action": {
                "recorded": first_actions,
                "avg_ms": self._average_first_action_ms(conn_none=True),
            },
            "actions_completed": actions_completed,
            "automations_created": automations,
            "ux_errors": ux_errors,
            "success_rate": round(actions_completed / max(actions_completed + ux_errors, 1), 3),
            "usage_by_mode": mode_uses,
            "sessions": sessions,
            "retention": {
                "active_days": active_days,
                "ratio": round(active_days / span, 3),
                "daily": [
                    {
                        "day": row["day"],
                        "actions": int(row["actions_completed"] or 0),
                        "sessions": int(row["sessions"] or 0),
                        "errors": int(row["ux_errors"] or 0),
                    }
                    for row in daily_rows
                ],
            },
        }

    def _average_first_action_ms(self, conn_none: bool = False) -> Optional[float]:
        try:
            with self._lock:
                conn = self._connect()
                try:
                    rows = conn.execute(
                        "SELECT details FROM product_events WHERE event_type = ?", (EVENT_FIRST_ACTION,)
                    ).fetchall()
                finally:
                    conn.close()
            values: List[float] = []
            for row in rows:
                try:
                    details = json.loads(row["details"])
                except (TypeError, ValueError):
                    details = {}
                if isinstance(details.get("latency_ms"), (int, float)):
                    values.append(float(details["latency_ms"]))
            return round(sum(values) / len(values), 1) if values else None
        except Exception:
            log.debug("first-action average unavailable", exc_info=True)
            return None


def time_import():
    import time

    return time
