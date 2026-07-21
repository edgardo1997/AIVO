import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol
import logging
import threading


def _sanitize(obj: Any) -> Any:
    """Recursively convert non-serializable types to JSON-safe values."""
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(i) for i in obj]
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


logger = logging.getLogger(__name__)


@dataclass
class OperationalMemoryConfig:
    execution_ttl: int = 300
    max_records: int = 50
    pending_action_ttl: int = 600
    max_pending_actions: int = 100
    eviction_interval: int = 60
    episodic_retention_days: int = 90
    environment_retention_days: int = 90
    pattern_min_evidence: int = 3


@dataclass
class ExecutionRecord:
    execution_id: str
    timestamp: str
    utterance: str
    intent: Dict[str, Any]
    plan: Dict[str, Any]
    decision: Optional[Dict[str, Any]]
    context_summary: Dict[str, Any]
    step_results: List[Dict[str, Any]]
    tool_result: Optional[Dict[str, Any]]
    error: Optional[str]
    duration_ms: float


@dataclass
class PendingActionRecord:
    action_id: str
    tool_id: str
    params: Dict[str, Any]
    reason: str
    created_at: str
    ttl_seconds: int
    risk_level: str = "unknown"
    plan_id: str = ""
    params_hash: str = ""
    identity_hash: str = ""
    redacted: bool = False


@dataclass
class EpisodicMemory:
    """A concise, user-scoped record of an execution outcome.

    This is operational product memory, not an audit event.  It must never be
    used to grant a permission or lower the risk of a future action.
    """

    memory_id: str
    user_id: str
    execution_id: str
    occurred_at: str
    summary: str
    intent_action: str
    intent_target: str
    tool_id: str
    outcome: str
    risk_score: Optional[float]
    tags: List[str]
    metadata: Dict[str, Any]
    expires_at: Optional[str] = None

    @property
    def source(self) -> str:
        return str(self.metadata.get("source", "orchestrator"))

    @property
    def confidence(self) -> float:
        try:
            return max(0.0, min(1.0, float(self.metadata.get("confidence", 0.0))))
        except (TypeError, ValueError):
            return 0.0


@dataclass
class MemoryPattern:
    pattern_id: str
    user_id: str
    pattern_type: str
    pattern_key: str
    evidence_count: int
    confidence: float
    first_seen: str
    last_seen: str
    data: Dict[str, Any]


@dataclass
class LearnedPreference:
    user_id: str
    key: str
    value: Any
    source: str
    evidence_count: int
    confidence: float
    created_at: str
    updated_at: str


@dataclass
class EnvironmentSnapshot:
    """Privacy-safe baseline used only to detect meaningful environment changes."""

    user_id: str
    fingerprint: str
    data: Dict[str, Any]
    source: str
    confidence: float
    observed_at: str


@dataclass
class EnvironmentChange:
    """Advisory-only, user-scoped observation; never an authorization signal."""

    change_id: str
    user_id: str
    change_type: str
    subject_id: str
    summary: str
    previous: Dict[str, Any]
    current: Dict[str, Any]
    source: str
    confidence: float
    detected_at: str
    expires_at: Optional[str]


class MemoryBackend(Protocol):
    def store_execution(self, record: ExecutionRecord) -> None: ...

    def update_execution(self, execution_id: str, **updates: Any) -> None: ...

    def get_execution(self, execution_id: str) -> Optional[ExecutionRecord]: ...

    def get_last_execution(self) -> Optional[ExecutionRecord]: ...

    def get_recent_executions(self, limit: int = 5) -> List[ExecutionRecord]: ...

    def get_session_history(
        self, session_id: str, limit: int = 10, *, user_id: Optional[str] = None
    ) -> List[ExecutionRecord]: ...

    def list_sessions(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]: ...

    def search_memory(self, user_id: str, query: str, limit: int = 50) -> List[ExecutionRecord]: ...

    def delete_session(self, session_id: str, user_id: str) -> int: ...

    def store_user_preference(
        self, session_id: str, key: str, value: Any, *, user_id: Optional[str] = None
    ) -> None: ...

    def get_user_preferences(self, session_id: str, *, user_id: Optional[str] = None) -> Dict[str, Any]: ...

    def remember_execution(self, user_id: str, record: ExecutionRecord) -> Optional[EpisodicMemory]: ...

    def get_episodes(
        self, user_id: str, limit: int = 10, *, min_confidence: float = 0.0
    ) -> List[EpisodicMemory]: ...

    def get_patterns(self, user_id: str, min_evidence: Optional[int] = None) -> List[MemoryPattern]: ...

    def learn_preference(
        self, user_id: str, key: str, value: Any, *, source: str = "explicit"
    ) -> LearnedPreference: ...

    def get_learned_preferences(
        self, user_id: str, *, min_confidence: float = 0.0
    ) -> Dict[str, LearnedPreference]: ...

    def get_environment_snapshot(self, user_id: str) -> Optional[EnvironmentSnapshot]: ...

    def store_environment_snapshot(self, snapshot: EnvironmentSnapshot) -> None: ...

    def store_environment_changes(self, changes: List[EnvironmentChange]) -> int: ...

    def get_environment_changes(
        self, user_id: str, limit: int = 10, *, min_confidence: float = 0.0
    ) -> List[EnvironmentChange]: ...

    def delete_environment_data(self, user_id: str) -> int: ...

    def store_pending_action(self, record: PendingActionRecord) -> None: ...

    def get_pending_action(self, action_id: str) -> Optional[PendingActionRecord]: ...

    def remove_pending_action(self, action_id: str) -> Optional[PendingActionRecord]: ...

    def list_pending_actions(self) -> List[PendingActionRecord]: ...

    def get_emergency_stop(self) -> bool: ...

    def set_emergency_stop(self, value: bool) -> None: ...

    def clear(self) -> None: ...

    def close(self) -> None: ...


class InMemoryBackend:
    def __init__(self, config: Optional[OperationalMemoryConfig] = None):
        self._config = config or OperationalMemoryConfig()
        self._records: Dict[str, ExecutionRecord] = {}
        self._pending: Dict[str, PendingActionRecord] = {}
        self._execution_order: List[str] = []
        self._emergency_stop: bool = False
        self._episodes: Dict[str, EpisodicMemory] = {}
        self._episode_order: List[str] = []
        self._patterns: Dict[tuple, MemoryPattern] = {}
        self._learned_preferences: Dict[str, Dict[str, LearnedPreference]] = {}
        self._environment_snapshots: Dict[str, EnvironmentSnapshot] = {}
        self._environment_changes: Dict[str, EnvironmentChange] = {}
        self._lock = threading.RLock()
        self._stop_eviction = threading.Event()
        self._eviction_thread = threading.Thread(
            target=self._eviction_loop,
            daemon=True,
        )
        self._eviction_thread.start()

    def store_execution(self, record: ExecutionRecord) -> None:
        with self._lock:
            is_new = record.execution_id not in self._records
            self._records[record.execution_id] = record
            if is_new:
                self._execution_order.append(record.execution_id)
            self._enforce_max_records()

    def update_execution(self, execution_id: str, **updates: Any) -> None:
        with self._lock:
            record = self._records.get(execution_id)
            if record is None:
                logger.warning("Cannot update unknown execution: %s", execution_id)
                return
            for key, value in updates.items():
                if hasattr(record, key):
                    setattr(record, key, value)

    def get_execution(self, execution_id: str) -> Optional[ExecutionRecord]:
        with self._lock:
            return self._records.get(execution_id)

    def get_last_execution(self) -> Optional[ExecutionRecord]:
        with self._lock:
            if not self._execution_order:
                return None
            eid = self._execution_order[-1]
            return self._records.get(eid)

    def get_recent_executions(self, limit: int = 5) -> List[ExecutionRecord]:
        with self._lock:
            recent = self._execution_order[-limit:]
            return [self._records[eid] for eid in recent if eid in self._records]

    def get_session_history(
        self, session_id: str, limit: int = 10, *, user_id: Optional[str] = None
    ) -> List[ExecutionRecord]:
        with self._lock:
            matched = []
            for eid in reversed(self._execution_order):
                rec = self._records.get(eid)
                if (
                    rec
                    and rec.context_summary.get("session_id") == session_id
                    and (user_id is None or rec.context_summary.get("user_id") == user_id)
                ):
                    matched.append(rec)
                    if len(matched) >= limit:
                        break
            return matched

    def list_sessions(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            grouped: Dict[str, List[ExecutionRecord]] = {}
            for record in self._records.values():
                if record.context_summary.get("user_id") != user_id:
                    continue
                session_id = record.context_summary.get("session_id")
                if session_id:
                    grouped.setdefault(session_id, []).append(record)
            sessions = []
            for session_id, records in grouped.items():
                records.sort(key=lambda item: item.timestamp, reverse=True)
                sessions.append(
                    {
                        "session_id": session_id,
                        "updated_at": records[0].timestamp,
                        "created_at": records[-1].timestamp,
                        "execution_count": len(records),
                        "last_utterance": records[0].utterance,
                    }
                )
            return sorted(sessions, key=lambda item: item["updated_at"], reverse=True)[:limit]

    def search_memory(self, user_id: str, query: str, limit: int = 50) -> List[ExecutionRecord]:
        with self._lock:
            needle = query.casefold()
            records = [self._records[eid] for eid in reversed(self._execution_order) if eid in self._records]
            return [
                record
                for record in records
                if record.context_summary.get("user_id") == user_id and needle in record.utterance.casefold()
            ][:limit]

    def delete_session(self, session_id: str, user_id: str) -> int:
        with self._lock:
            ids = [
                eid
                for eid, record in self._records.items()
                if record.context_summary.get("session_id") == session_id
                and record.context_summary.get("user_id") == user_id
            ]
            for eid in ids:
                self._records.pop(eid, None)
                self._episodes.pop(eid, None)
                if eid in self._execution_order:
                    self._execution_order.remove(eid)
                if eid in self._episode_order:
                    self._episode_order.remove(eid)
            still_used = any(
                record.context_summary.get("session_id") == session_id for record in self._records.values()
            )
            if hasattr(self, "_preferences") and not still_used:
                self._preferences.pop((user_id, session_id), None)
                self._preferences.pop(("", session_id), None)
            self._rebuild_patterns(user_id)
            return len(ids)

    def store_user_preference(
        self, session_id: str, key: str, value: Any, *, user_id: Optional[str] = None
    ) -> None:
        if not hasattr(self, "_preferences"):
            self._preferences: Dict[str, Dict[str, Any]] = {}
        with self._lock:
            self._preferences.setdefault((user_id or "", session_id), {})[key] = value

    def get_user_preferences(self, session_id: str, *, user_id: Optional[str] = None) -> Dict[str, Any]:
        if not hasattr(self, "_preferences"):
            return {}
        with self._lock:
            return dict(self._preferences.get((user_id or "", session_id), {}))

    def remember_execution(self, user_id: str, record: ExecutionRecord) -> Optional[EpisodicMemory]:
        if not user_id:
            return None
        episode = _episode_from_execution(user_id, record, self._config)
        with self._lock:
            if episode.execution_id not in self._episodes:
                self._episode_order.append(episode.execution_id)
            self._episodes[episode.execution_id] = episode
            self._observe_pattern(episode)
        return episode

    def get_episodes(
        self, user_id: str, limit: int = 10, *, min_confidence: float = 0.0
    ) -> List[EpisodicMemory]:
        now = datetime.now(timezone.utc)
        with self._lock:
            return [
                self._episodes[eid]
                for eid in reversed(self._episode_order)
                if self._episodes[eid].user_id == user_id
                and self._episodes[eid].confidence >= min_confidence
                and not _is_expired(self._episodes[eid].expires_at, now)
            ][: max(0, limit)]

    def get_patterns(self, user_id: str, min_evidence: Optional[int] = None) -> List[MemoryPattern]:
        threshold = self._config.pattern_min_evidence if min_evidence is None else min_evidence
        with self._lock:
            return sorted(
                [p for p in self._patterns.values() if p.user_id == user_id and p.evidence_count >= threshold],
                key=lambda p: (-p.evidence_count, p.pattern_key),
            )

    def learn_preference(self, user_id: str, key: str, value: Any, *, source: str = "explicit") -> LearnedPreference:
        _validate_learned_preference(key, source)
        now = _utc_now()
        with self._lock:
            previous = self._learned_preferences.setdefault(user_id, {}).get(key)
            pref = LearnedPreference(
                user_id,
                key,
                value,
                source,
                (previous.evidence_count + 1) if previous else 1,
                1.0 if source == "explicit" else min(0.95, ((previous.confidence if previous else 0.5) + 0.1)),
                previous.created_at if previous else now,
                now,
            )
            self._learned_preferences[user_id][key] = pref
            return pref

    def get_learned_preferences(
        self, user_id: str, *, min_confidence: float = 0.0
    ) -> Dict[str, LearnedPreference]:
        with self._lock:
            return {
                key: pref
                for key, pref in self._learned_preferences.get(user_id, {}).items()
                if pref.confidence >= min_confidence
            }

    def get_environment_snapshot(self, user_id: str) -> Optional[EnvironmentSnapshot]:
        with self._lock:
            return self._environment_snapshots.get(user_id)

    def store_environment_snapshot(self, snapshot: EnvironmentSnapshot) -> None:
        if not snapshot.user_id:
            raise ValueError("Environment snapshots require a user_id")
        with self._lock:
            self._environment_snapshots[snapshot.user_id] = snapshot

    def store_environment_changes(self, changes: List[EnvironmentChange]) -> int:
        stored = 0
        with self._lock:
            for change in changes:
                if not change.user_id or change.change_id in self._environment_changes:
                    continue
                self._environment_changes[change.change_id] = change
                stored += 1
        return stored

    def get_environment_changes(
        self, user_id: str, limit: int = 10, *, min_confidence: float = 0.0
    ) -> List[EnvironmentChange]:
        now = datetime.now(timezone.utc)
        with self._lock:
            matches = [
                change
                for change in self._environment_changes.values()
                if change.user_id == user_id
                and change.confidence >= min_confidence
                and not _is_expired(change.expires_at, now)
            ]
        return sorted(matches, key=lambda change: change.detected_at, reverse=True)[: max(0, limit)]

    def delete_environment_data(self, user_id: str) -> int:
        with self._lock:
            ids = [change_id for change_id, change in self._environment_changes.items() if change.user_id == user_id]
            for change_id in ids:
                self._environment_changes.pop(change_id, None)
            removed_snapshot = self._environment_snapshots.pop(user_id, None) is not None
        return len(ids) + int(removed_snapshot)

    def _observe_pattern(self, episode: EpisodicMemory) -> None:
        if not episode.intent_target:
            return
        key = (episode.user_id, "intent_target", episode.intent_target)
        existing = self._patterns.get(key)
        now = episode.occurred_at
        count = (existing.evidence_count + 1) if existing else 1
        self._patterns[key] = MemoryPattern(
            pattern_id=_pattern_id(*key),
            user_id=episode.user_id,
            pattern_type="intent_target",
            pattern_key=episode.intent_target,
            evidence_count=count,
            confidence=min(0.95, count / 10),
            first_seen=existing.first_seen if existing else now,
            last_seen=now,
            data={"tool_id": episode.tool_id, "latest_outcome": episode.outcome},
        )

    def _rebuild_patterns(self, user_id: str) -> None:
        self._patterns = {key: value for key, value in self._patterns.items() if value.user_id != user_id}
        for episode in self._episodes.values():
            if episode.user_id == user_id and not _is_expired(episode.expires_at):
                self._observe_pattern(episode)

    def store_pending_action(self, record: PendingActionRecord) -> None:
        with self._lock:
            if len(self._pending) >= self._config.max_pending_actions:
                raise RuntimeError(f"Pending action limit ({self._config.max_pending_actions}) reached")
            self._pending[record.action_id] = record

    def get_pending_action(self, action_id: str) -> Optional[PendingActionRecord]:
        with self._lock:
            return self._pending.get(action_id)

    def remove_pending_action(self, action_id: str) -> Optional[PendingActionRecord]:
        with self._lock:
            return self._pending.pop(action_id, None)

    def list_pending_actions(self) -> List[PendingActionRecord]:
        with self._lock:
            return list(self._pending.values())

    def get_emergency_stop(self) -> bool:
        with self._lock:
            return self._emergency_stop

    def set_emergency_stop(self, value: bool) -> None:
        with self._lock:
            self._emergency_stop = value

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
            self._pending.clear()
            self._execution_order.clear()
            self._emergency_stop = False
            self._episodes.clear()
            self._episode_order.clear()
            self._patterns.clear()
            self._learned_preferences.clear()
            self._environment_snapshots.clear()
            self._environment_changes.clear()

    def close(self) -> None:
        self._stop_eviction.set()
        if self._eviction_thread.is_alive():
            self._eviction_thread.join(timeout=2)

    def _enforce_max_records(self) -> None:
        while len(self._records) > self._config.max_records:
            oldest_id = self._execution_order.pop(0)
            del self._records[oldest_id]

    def _eviction_loop(self) -> None:
        while not self._stop_eviction.is_set():
            if self._stop_eviction.wait(self._config.eviction_interval):
                break
            try:
                self._evict_expired()
            except Exception as e:
                logger.warning("Eviction error: %s", e)

    def _evict_expired(self) -> None:
        now = datetime.now(timezone.utc)
        with self._lock:
            exec_threshold = now - timedelta(seconds=self._config.execution_ttl)
            to_remove = []
            for eid in list(self._execution_order):
                record = self._records.get(eid)
                if record and self._parse_ts(record.timestamp) < exec_threshold:
                    to_remove.append(eid)
            for eid in to_remove:
                del self._records[eid]
                self._execution_order.remove(eid)

            pend_threshold = now - timedelta(seconds=self._config.pending_action_ttl)
            expired_pending = [
                aid for aid, rec in self._pending.items() if self._parse_ts(rec.created_at) < pend_threshold
            ]
            for aid in expired_pending:
                del self._pending[aid]

    @staticmethod
    def _parse_ts(ts: str) -> datetime:
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return datetime.now(timezone.utc)


class SQLiteBackend:
    def __init__(self, db=None, config: Optional[OperationalMemoryConfig] = None):
        if db is None:
            # The sidecar is added to sys.path by the application bootstrap. Using
            # the top-level repository package avoids loading a second singleton as
            # both `repositories.database` and `sidecar.repositories.database`.
            from repositories.database import DatabaseManager

            db = DatabaseManager()
        self._db = db
        self._config = config or OperationalMemoryConfig()

    def store_execution(self, record: ExecutionRecord) -> None:
        self._db.execute(
            """INSERT OR REPLACE INTO execution_history
               (execution_id, timestamp, utterance, intent, plan, decision,
                context_summary, step_results, tool_result, error, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.execution_id,
                record.timestamp,
                record.utterance,
                json.dumps(record.intent),
                json.dumps(record.plan),
                json.dumps(record.decision) if record.decision else None,
                json.dumps(record.context_summary),
                json.dumps(record.step_results),
                json.dumps(record.tool_result) if record.tool_result else None,
                record.error,
                record.duration_ms,
            ),
        )
        self._db.commit()

    def update_execution(self, execution_id: str, **updates: Any) -> None:
        allowed_columns = {
            "timestamp",
            "utterance",
            "intent",
            "plan",
            "decision",
            "context_summary",
            "step_results",
            "tool_result",
            "error",
            "duration_ms",
        }
        sets = []
        params = []
        for key, value in updates.items():
            if key not in allowed_columns:
                raise ValueError(f"Invalid column name: {key}")
            sets.append(f"{key} = ?")
            params.append(json.dumps(value) if isinstance(value, (dict, list)) else value)
        params.append(execution_id)
        sql = f"UPDATE execution_history SET {', '.join(sets)} WHERE execution_id = ?"  # nosec B608 - strict allowlist above
        self._db.execute(sql, tuple(params))
        self._db.commit()

    def get_execution(self, execution_id: str) -> Optional[ExecutionRecord]:
        row = self._db.fetchone("SELECT * FROM execution_history WHERE execution_id = ?", (execution_id,))
        return self._row_to_record(row) if row else None

    def get_last_execution(self) -> Optional[ExecutionRecord]:
        row = self._db.fetchone("SELECT * FROM execution_history ORDER BY rowid DESC LIMIT 1")
        return self._row_to_record(row) if row else None

    def get_recent_executions(self, limit: int = 5) -> List[ExecutionRecord]:
        rows = self._db.fetchall("SELECT * FROM execution_history ORDER BY rowid DESC LIMIT ?", (limit,))
        return [self._row_to_record(r) for r in rows if r]

    def get_session_history(
        self, session_id: str, limit: int = 10, *, user_id: Optional[str] = None
    ) -> List[ExecutionRecord]:
        owner_clause = " AND json_extract(context_summary, '$.user_id') = ?" if user_id is not None else ""
        params: tuple[Any, ...] = (session_id, user_id, limit) if user_id is not None else (session_id, limit)
        rows = self._db.fetchall(
            f"""SELECT * FROM execution_history
               WHERE json_extract(context_summary, '$.session_id') = ?{owner_clause}
               ORDER BY rowid DESC LIMIT ?""",  # nosec B608 - clause is selected from constants above
            params,
        )
        return [self._row_to_record(r) for r in rows if r]

    def list_sessions(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self._db.fetchall(
            """WITH scoped AS (
                   SELECT rowid AS execution_rowid,
                          json_extract(context_summary, '$.session_id') AS session_id,
                          timestamp,
                          utterance
                   FROM execution_history
                   WHERE json_extract(context_summary, '$.user_id') = ?
                     AND json_extract(context_summary, '$.session_id') IS NOT NULL
               ), ranked AS (
                   SELECT session_id,
                          timestamp,
                          utterance,
                          ROW_NUMBER() OVER (
                              PARTITION BY session_id
                              ORDER BY timestamp DESC, execution_rowid DESC
                          ) AS recency
                   FROM scoped
               )
               SELECT session_id,
                      MIN(timestamp) AS created_at,
                      MAX(timestamp) AS updated_at,
                      COUNT(*) AS execution_count,
                      MAX(CASE WHEN recency = 1 THEN utterance END) AS last_utterance
               FROM ranked
               GROUP BY session_id
               ORDER BY updated_at DESC
               LIMIT ?""",
            (user_id, max(1, min(limit, 200))),
        )
        return [
            {
                **dict(row),
                "last_utterance": row.get("last_utterance") or "",
            }
            for row in rows
        ]

    def search_memory(self, user_id: str, query: str, limit: int = 50) -> List[ExecutionRecord]:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = self._db.fetchall(
            """SELECT * FROM execution_history
               WHERE json_extract(context_summary, '$.user_id') = ?
                 AND utterance LIKE ? ESCAPE '\\'
               ORDER BY timestamp DESC LIMIT ?""",
            (user_id, f"%{escaped}%", max(1, min(limit, 200))),
        )
        return [self._row_to_record(row) for row in rows]

    def delete_session(self, session_id: str, user_id: str) -> int:
        rows = self._db.fetchall(
            """SELECT execution_id FROM execution_history
               WHERE json_extract(context_summary, '$.session_id') = ?
                 AND json_extract(context_summary, '$.user_id') = ?""",
            (session_id, user_id),
        )
        execution_ids = [row["execution_id"] for row in rows]
        for execution_id in execution_ids:
            self._db.execute(
                "DELETE FROM episodic_memory WHERE execution_id = ? AND user_id = ?", (execution_id, user_id)
            )
        self._db.execute(
            """DELETE FROM execution_history
               WHERE json_extract(context_summary, '$.session_id') = ?
                 AND json_extract(context_summary, '$.user_id') = ?""",
            (session_id, user_id),
        )
        remaining = self._db.fetchone(
            """SELECT COUNT(*) AS count FROM execution_history
               WHERE json_extract(context_summary, '$.session_id') = ?""",
            (session_id,),
        )
        if not remaining or remaining["count"] == 0:
            self._db.execute("DELETE FROM user_preferences WHERE session_id = ?", (session_id,))
        self._db.execute(
            "DELETE FROM session_preferences WHERE user_id = ? AND session_id = ?", (user_id, session_id)
        )
        self._rebuild_patterns(user_id)
        self._db.commit()
        return len(execution_ids)

    def store_user_preference(
        self, session_id: str, key: str, value: Any, *, user_id: Optional[str] = None
    ) -> None:
        if user_id is not None:
            self._db.execute(
                """INSERT INTO session_preferences (user_id, session_id, key, value)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id, session_id, key) DO UPDATE SET
                     value = excluded.value, updated_at = datetime('now')""",
                (user_id, session_id, key, json.dumps(value)),
            )
            self._db.commit()
            return
        self._db.execute(
            """INSERT INTO user_preferences (session_id, key, value)
               VALUES (?, ?, ?)
               ON CONFLICT(session_id, key) DO UPDATE SET value = excluded.value""",
            (session_id, key, json.dumps(value)),
        )
        self._db.commit()

    def get_user_preferences(self, session_id: str, *, user_id: Optional[str] = None) -> Dict[str, Any]:
        if user_id is not None:
            rows = self._db.fetchall(
                "SELECT key, value FROM session_preferences WHERE user_id = ? AND session_id = ?",
                (user_id, session_id),
            )
            return {r["key"]: json.loads(r["value"]) for r in rows}
        rows = self._db.fetchall(
            "SELECT key, value FROM user_preferences WHERE session_id = ?",
            (session_id,),
        )
        return {r["key"]: json.loads(r["value"]) for r in rows}

    def remember_execution(self, user_id: str, record: ExecutionRecord) -> Optional[EpisodicMemory]:
        if not user_id:
            return None
        episode = _episode_from_execution(user_id, record, self._config)
        with self._db.transaction(immediate=True) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO episodic_memory
                   (memory_id, user_id, execution_id, occurred_at, summary, intent_action,
                    intent_target, tool_id, outcome, risk_score, tags, metadata, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    episode.memory_id,
                    episode.user_id,
                    episode.execution_id,
                    episode.occurred_at,
                    episode.summary,
                    episode.intent_action,
                    episode.intent_target,
                    episode.tool_id,
                    episode.outcome,
                    episode.risk_score,
                    json.dumps(episode.tags),
                    json.dumps(episode.metadata),
                    episode.expires_at,
                ),
            )
            self._observe_pattern_in_tx(episode, conn)
        return episode

    def _observe_pattern_in_tx(self, episode: EpisodicMemory, conn) -> None:
        if not episode.intent_target:
            return
        row = conn.execute(
            """SELECT * FROM memory_patterns WHERE user_id = ? AND pattern_type = ? AND pattern_key = ?""",
            (episode.user_id, "intent_target", episode.intent_target),
        ).fetchone()
        count = (row["evidence_count"] + 1) if row else 1
        first_seen = row["first_seen"] if row else episode.occurred_at
        conn.execute(
            """INSERT INTO memory_patterns
               (pattern_id, user_id, pattern_type, pattern_key, evidence_count, confidence, first_seen, last_seen, data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, pattern_type, pattern_key) DO UPDATE SET
                 evidence_count = excluded.evidence_count, confidence = excluded.confidence,
                 last_seen = excluded.last_seen, data = excluded.data""",
            (
                _pattern_id(episode.user_id, "intent_target", episode.intent_target),
                episode.user_id,
                "intent_target",
                episode.intent_target,
                count,
                min(0.95, count / 10),
                first_seen,
                episode.occurred_at,
                json.dumps({"tool_id": episode.tool_id, "latest_outcome": episode.outcome}),
            ),
        )

    def get_episodes(
        self, user_id: str, limit: int = 10, *, min_confidence: float = 0.0
    ) -> List[EpisodicMemory]:
        rows = self._db.fetchall(
            """SELECT * FROM episodic_memory
               WHERE user_id = ? AND (expires_at IS NULL OR expires_at > ?)
               ORDER BY occurred_at DESC LIMIT ?""",
            (user_id, _utc_now(), max(0, limit)),
        )
        return [episode for row in rows if (episode := self._row_to_episode(row)).confidence >= min_confidence]

    def get_patterns(self, user_id: str, min_evidence: Optional[int] = None) -> List[MemoryPattern]:
        threshold = self._config.pattern_min_evidence if min_evidence is None else min_evidence
        rows = self._db.fetchall(
            """SELECT * FROM memory_patterns WHERE user_id = ? AND evidence_count >= ?
               ORDER BY evidence_count DESC, pattern_key ASC""",
            (user_id, threshold),
        )
        return [self._row_to_pattern(row) for row in rows]

    def learn_preference(self, user_id: str, key: str, value: Any, *, source: str = "explicit") -> LearnedPreference:
        _validate_learned_preference(key, source)
        now = _utc_now()
        existing = self._db.fetchone(
            "SELECT * FROM learned_preferences WHERE user_id = ? AND key = ?",
            (user_id, key),
        )
        evidence = (existing["evidence_count"] + 1) if existing else 1
        previous_confidence = float(existing["confidence"]) if existing else 0.5
        confidence = 1.0 if source == "explicit" else min(0.95, previous_confidence + 0.1)
        created_at = existing["created_at"] if existing else now
        self._db.execute(
            """INSERT INTO learned_preferences
               (user_id, key, value, source, evidence_count, confidence, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value,
                 source = excluded.source, evidence_count = excluded.evidence_count,
                 confidence = excluded.confidence, updated_at = excluded.updated_at""",
            (user_id, key, json.dumps(value), source, evidence, confidence, created_at, now),
        )
        self._db.commit()
        return LearnedPreference(user_id, key, value, source, evidence, confidence, created_at, now)

    def get_learned_preferences(
        self, user_id: str, *, min_confidence: float = 0.0
    ) -> Dict[str, LearnedPreference]:
        rows = self._db.fetchall(
            "SELECT * FROM learned_preferences WHERE user_id = ? AND confidence >= ?",
            (user_id, min_confidence),
        )
        return {row["key"]: self._row_to_preference(row) for row in rows}

    def get_environment_snapshot(self, user_id: str) -> Optional[EnvironmentSnapshot]:
        row = self._db.fetchone("SELECT * FROM environment_snapshots WHERE user_id = ?", (user_id,))
        if not row:
            return None
        return EnvironmentSnapshot(
            user_id=row["user_id"],
            fingerprint=row["fingerprint"],
            data=json.loads(row["data"]),
            source=row["source"],
            confidence=float(row["confidence"]),
            observed_at=row["observed_at"],
        )

    def store_environment_snapshot(self, snapshot: EnvironmentSnapshot) -> None:
        if not snapshot.user_id:
            raise ValueError("Environment snapshots require a user_id")
        self._db.execute(
            """INSERT INTO environment_snapshots
               (user_id, fingerprint, data, source, confidence, observed_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET fingerprint = excluded.fingerprint,
                 data = excluded.data, source = excluded.source,
                 confidence = excluded.confidence, observed_at = excluded.observed_at""",
            (
                snapshot.user_id,
                snapshot.fingerprint,
                json.dumps(_sanitize(snapshot.data), sort_keys=True),
                snapshot.source,
                snapshot.confidence,
                snapshot.observed_at,
            ),
        )
        self._db.commit()

    def store_environment_changes(self, changes: List[EnvironmentChange]) -> int:
        stored = 0
        for change in changes:
            if not change.user_id:
                continue
            cursor = self._db.execute(
                """INSERT OR IGNORE INTO environment_changes
                   (change_id, user_id, change_type, subject_id, summary, previous,
                    current, source, confidence, detected_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    change.change_id,
                    change.user_id,
                    change.change_type,
                    change.subject_id,
                    change.summary,
                    json.dumps(_sanitize(change.previous), sort_keys=True),
                    json.dumps(_sanitize(change.current), sort_keys=True),
                    change.source,
                    change.confidence,
                    change.detected_at,
                    change.expires_at,
                ),
            )
            stored += max(0, cursor.rowcount)
        if changes:
            self._db.commit()
        return stored

    def get_environment_changes(
        self, user_id: str, limit: int = 10, *, min_confidence: float = 0.0
    ) -> List[EnvironmentChange]:
        rows = self._db.fetchall(
            """SELECT * FROM environment_changes
               WHERE user_id = ? AND confidence >= ?
                 AND (expires_at IS NULL OR expires_at > ?)
               ORDER BY detected_at DESC LIMIT ?""",
            (user_id, min_confidence, _utc_now(), max(0, min(limit, 200))),
        )
        return [self._row_to_environment_change(row) for row in rows]

    def delete_environment_data(self, user_id: str) -> int:
        row = self._db.fetchone(
            """SELECT
                 (SELECT COUNT(*) FROM environment_changes WHERE user_id = ?) +
                 (SELECT COUNT(*) FROM environment_snapshots WHERE user_id = ?) AS count""",
            (user_id, user_id),
        )
        self._db.execute("DELETE FROM environment_changes WHERE user_id = ?", (user_id,))
        self._db.execute("DELETE FROM environment_snapshots WHERE user_id = ?", (user_id,))
        self._db.commit()
        return int(row["count"]) if row else 0

    def _observe_pattern(self, episode: EpisodicMemory) -> None:
        if not episode.intent_target:
            return
        row = self._db.fetchone(
            """SELECT * FROM memory_patterns WHERE user_id = ? AND pattern_type = ? AND pattern_key = ?""",
            (episode.user_id, "intent_target", episode.intent_target),
        )
        count = (row["evidence_count"] + 1) if row else 1
        first_seen = row["first_seen"] if row else episode.occurred_at
        self._db.execute(
            """INSERT INTO memory_patterns
               (pattern_id, user_id, pattern_type, pattern_key, evidence_count, confidence, first_seen, last_seen, data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, pattern_type, pattern_key) DO UPDATE SET
                 evidence_count = excluded.evidence_count, confidence = excluded.confidence,
                 last_seen = excluded.last_seen, data = excluded.data""",
            (
                _pattern_id(episode.user_id, "intent_target", episode.intent_target),
                episode.user_id,
                "intent_target",
                episode.intent_target,
                count,
                min(0.95, count / 10),
                first_seen,
                episode.occurred_at,
                json.dumps({"tool_id": episode.tool_id, "latest_outcome": episode.outcome}),
            ),
        )

    def _rebuild_patterns(self, user_id: str) -> None:
        self._db.execute("DELETE FROM memory_patterns WHERE user_id = ?", (user_id,))
        rows = self._db.fetchall(
            """SELECT * FROM episodic_memory
               WHERE user_id = ? AND (expires_at IS NULL OR expires_at > ?)
               ORDER BY occurred_at ASC""",
            (user_id, _utc_now()),
        )
        for row in rows:
            self._observe_pattern(self._row_to_episode(row))

    def store_pending_action(self, record: PendingActionRecord) -> None:
        self._db.execute(
            """INSERT OR REPLACE INTO pending_actions
               (action_id, tool_id, params, reason, created_at, ttl_seconds, confirmed)
               VALUES (?, ?, ?, ?, ?, ?, 0)""",
            (
                record.action_id,
                record.tool_id,
                json.dumps(_sanitize(record.params)),
                record.reason,
                record.created_at,
                record.ttl_seconds,
            ),
        )
        self._db.commit()

    def get_pending_action(self, action_id: str) -> Optional[PendingActionRecord]:
        row = self._db.fetchone("SELECT * FROM pending_actions WHERE action_id = ?", (action_id,))
        return self._row_to_pending(row) if row else None

    def remove_pending_action(self, action_id: str) -> Optional[PendingActionRecord]:
        rec = self.get_pending_action(action_id)
        if rec:
            self._db.execute("DELETE FROM pending_actions WHERE action_id = ?", (action_id,))
            self._db.commit()
        return rec

    def list_pending_actions(self) -> List[PendingActionRecord]:
        rows = self._db.fetchall("SELECT * FROM pending_actions ORDER BY created_at DESC")
        return [self._row_to_pending(r) for r in rows]

    def get_emergency_stop(self) -> bool:
        row = self._db.fetchone("SELECT value FROM emergency_stop WHERE id = 1")
        return bool(row["value"]) if row else False

    def set_emergency_stop(self, value: bool) -> None:
        self._db.execute("UPDATE emergency_stop SET value = ? WHERE id = 1", (1 if value else 0,))
        self._db.commit()

    def clear(self) -> None:
        self._db.execute("DELETE FROM execution_history")
        self._db.execute("DELETE FROM pending_actions")
        self._db.execute("DELETE FROM user_preferences")
        self._db.execute("DELETE FROM session_preferences")
        self._db.execute("DELETE FROM episodic_memory")
        self._db.execute("DELETE FROM memory_patterns")
        self._db.execute("DELETE FROM learned_preferences")
        self._db.execute("DELETE FROM environment_changes")
        self._db.execute("DELETE FROM environment_snapshots")
        self._db.execute("UPDATE emergency_stop SET value = 0 WHERE id = 1")
        self._db.commit()

    def close(self) -> None:
        pass

    def _row_to_record(self, row: dict) -> ExecutionRecord:
        return ExecutionRecord(
            execution_id=row["execution_id"],
            timestamp=row["timestamp"],
            utterance=row.get("utterance", ""),
            intent=json.loads(row.get("intent", "{}")),
            plan=json.loads(row.get("plan", "{}")),
            decision=json.loads(row["decision"]) if row.get("decision") else None,
            context_summary=json.loads(row.get("context_summary", "{}")),
            step_results=json.loads(row.get("step_results", "[]")),
            tool_result=json.loads(row["tool_result"]) if row.get("tool_result") else None,
            error=row.get("error"),
            duration_ms=row.get("duration_ms", 0),
        )

    def _row_to_pending(self, row: dict) -> PendingActionRecord:
        return PendingActionRecord(
            action_id=row["action_id"],
            tool_id=row["tool_id"],
            params=json.loads(row.get("params", "{}")),
            reason=row.get("reason", ""),
            created_at=row.get("created_at", ""),
            ttl_seconds=row.get("ttl_seconds", 600),
        )

    @staticmethod
    def _row_to_environment_change(row: dict) -> EnvironmentChange:
        return EnvironmentChange(
            change_id=row["change_id"],
            user_id=row["user_id"],
            change_type=row["change_type"],
            subject_id=row["subject_id"],
            summary=row["summary"],
            previous=json.loads(row["previous"]),
            current=json.loads(row["current"]),
            source=row["source"],
            confidence=float(row["confidence"]),
            detected_at=row["detected_at"],
            expires_at=row.get("expires_at"),
        )

    @staticmethod
    def _row_to_episode(row: dict) -> EpisodicMemory:
        return EpisodicMemory(
            memory_id=row["memory_id"],
            user_id=row["user_id"],
            execution_id=row["execution_id"],
            occurred_at=row["occurred_at"],
            summary=row["summary"],
            intent_action=row["intent_action"],
            intent_target=row["intent_target"],
            tool_id=row["tool_id"],
            outcome=row["outcome"],
            risk_score=row["risk_score"],
            tags=json.loads(row["tags"]),
            metadata=json.loads(row["metadata"]),
            expires_at=row["expires_at"],
        )

    @staticmethod
    def _row_to_pattern(row: dict) -> MemoryPattern:
        return MemoryPattern(
            pattern_id=row["pattern_id"],
            user_id=row["user_id"],
            pattern_type=row["pattern_type"],
            pattern_key=row["pattern_key"],
            evidence_count=row["evidence_count"],
            confidence=row["confidence"],
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
            data=json.loads(row["data"]),
        )

    @staticmethod
    def _row_to_preference(row: dict) -> LearnedPreference:
        return LearnedPreference(
            user_id=row["user_id"],
            key=row["key"],
            value=json.loads(row["value"]),
            source=row["source"],
            evidence_count=row["evidence_count"],
            confidence=row["confidence"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


_FORBIDDEN_PREFERENCE_PREFIXES = ("permission", "policy", "risk", "auth", "security", "execution")


def _validate_learned_preference(key: str, source: str) -> None:
    if not key or not key.replace(".", "").replace("_", "").isalnum():
        raise ValueError("Preference key must be a non-empty dotted identifier")
    if key.lower().startswith(_FORBIDDEN_PREFERENCE_PREFIXES):
        raise ValueError("Preferences cannot control permissions, policy, risk, authentication, security, or execution")
    if source not in {"explicit", "observed"}:
        raise ValueError("Preference source must be 'explicit' or 'observed'")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_expired(expires_at: Optional[str], now: Optional[datetime] = None) -> bool:
    if not expires_at:
        return False
    reference = now or datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        # Corrupt freshness metadata is not trusted as active memory.
        return True
    return parsed <= reference


def _pattern_id(user_id: str, pattern_type: str, pattern_key: str) -> str:
    return hashlib.sha256(f"{user_id}:{pattern_type}:{pattern_key}".encode("utf-8")).hexdigest()[:24]


def _episode_from_execution(user_id: str, record: ExecutionRecord, config: OperationalMemoryConfig) -> EpisodicMemory:
    intent = record.intent or {}
    plan = record.plan or {}
    tool_result = record.tool_result or {}
    outcome = "failed" if record.error or tool_result.get("success") is False else "succeeded"
    target = str(intent.get("target", ""))
    action = str(intent.get("action", ""))
    tool_id = str(tool_result.get("tool_id", ""))
    risk_score = plan.get("risk_score")
    tags = [tag for tag in (action, target, outcome) if tag]
    expires_at = (
        (datetime.now(timezone.utc) + timedelta(days=config.episodic_retention_days)).isoformat().replace("+00:00", "Z")
    )
    summary = f"{action or 'action'} → {target or tool_id or 'unknown'}: {outcome}"
    return EpisodicMemory(
        memory_id=hashlib.sha256(f"episode:{user_id}:{record.execution_id}".encode("utf-8")).hexdigest()[:24],
        user_id=user_id,
        execution_id=record.execution_id,
        occurred_at=record.timestamp,
        summary=summary,
        intent_action=action,
        intent_target=target,
        tool_id=tool_id,
        outcome=outcome,
        risk_score=float(risk_score) if risk_score is not None else None,
        tags=tags,
        metadata={
            "source": "orchestrator.execution",
            "confidence": _execution_memory_confidence(record, outcome),
            "duration_ms": record.duration_ms,
            "has_error": bool(record.error),
            "session_id": record.context_summary.get("session_id"),
        },
        expires_at=expires_at,
    )


def _execution_memory_confidence(record: ExecutionRecord, outcome: str) -> float:
    """Score factual execution memory without granting it authority.

    A completed tool result is direct evidence. Conversation-only and failed
    operations remain useful context, but are deliberately less trustworthy.
    """
    if record.tool_result:
        return 0.95 if outcome == "succeeded" else 0.85
    if record.error:
        return 0.75
    return 0.65
