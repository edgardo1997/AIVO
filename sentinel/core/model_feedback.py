import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

from .model_router import TaskType

logger = logging.getLogger(__name__)


@dataclass
class ModelFeedback:
    provider_id: str
    model: str
    task_type: TaskType
    success: bool
    duration_ms: float
    timestamp: str
    error: Optional[str] = None


@dataclass
class ProviderTaskStats:
    provider_id: str
    task_type: TaskType
    total: int
    successes: int
    failures: int
    avg_duration_ms: float
    success_rate: float


class ModelFeedbackStore:
    def __init__(self, max_records: int = 10000, db_path: Optional[str] = None):
        self._records: List[ModelFeedback] = []
        self._max_records = max_records
        self._db_path = db_path
        self._local = threading.local()

        if self._db_path:
            self._init_db()
            self._load_from_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS model_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id TEXT NOT NULL,
                model TEXT NOT NULL,
                task_type TEXT NOT NULL,
                success INTEGER NOT NULL,
                duration_ms REAL NOT NULL,
                timestamp TEXT NOT NULL,
                error TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_feedback_provider
            ON model_feedback (provider_id, task_type)
        """)
        conn.commit()

    def _load_from_db(self) -> None:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT provider_id, model, task_type, success, duration_ms, timestamp, error "
            "FROM model_feedback ORDER BY id"
        )
        for row in cursor:
            self._records.append(ModelFeedback(
                provider_id=row["provider_id"],
                model=row["model"],
                task_type=TaskType(row["task_type"]),
                success=bool(row["success"]),
                duration_ms=row["duration_ms"],
                timestamp=row["timestamp"],
                error=row["error"],
            ))
        logger.debug("Loaded %d feedback records from %s", len(self._records), self._db_path)

    def _persist(self, fb: ModelFeedback) -> None:
        if not self._db_path:
            return
        try:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO model_feedback (provider_id, model, task_type, success, duration_ms, timestamp, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (fb.provider_id, fb.model, fb.task_type.value, int(fb.success),
                 fb.duration_ms, fb.timestamp, fb.error),
            )
            conn.commit()
        except Exception as e:
            logger.warning("Failed to persist feedback: %s", e)

    def record(
        self,
        provider_id: str,
        model: str,
        task_type: TaskType,
        success: bool,
        duration_ms: float,
        error: Optional[str] = None,
    ) -> None:
        fb = ModelFeedback(
            provider_id=provider_id,
            model=model,
            task_type=task_type,
            success=success,
            duration_ms=duration_ms,
            timestamp=datetime.now(timezone.utc).isoformat(),
            error=error,
        )
        self._records.append(fb)
        if len(self._records) > self._max_records:
            removed = self._records.pop(0)
        self._persist(fb)
        logger.debug(
            "Feedback recorded: %s/%s %s success=%s %.0fms",
            provider_id, model, task_type.value, success, duration_ms,
        )

    def get_stats(
        self,
        provider_id: Optional[str] = None,
        task_type: Optional[TaskType] = None,
    ) -> List[ProviderTaskStats]:
        filtered = self._records
        if provider_id:
            filtered = [r for r in filtered if r.provider_id == provider_id]
        if task_type:
            filtered = [r for r in filtered if r.task_type == task_type]

        groups: Dict[tuple, List[ModelFeedback]] = {}
        for r in filtered:
            key = (r.provider_id, r.task_type)
            groups.setdefault(key, []).append(r)

        result = []
        for (pid, tt), recs in groups.items():
            successes = sum(1 for r in recs if r.success)
            total = len(recs)
            avg_dur = sum(r.duration_ms for r in recs) / total if total else 0.0
            result.append(ProviderTaskStats(
                provider_id=pid,
                task_type=tt,
                total=total,
                successes=successes,
                failures=total - successes,
                avg_duration_ms=round(avg_dur, 1),
                success_rate=round(successes / total, 3) if total else 0.0,
            ))
        result.sort(key=lambda s: s.success_rate, reverse=True)
        return result

    def get_success_rate(self, provider_id: str, task_type: TaskType) -> float:
        stats = self.get_stats(provider_id=provider_id, task_type=task_type)
        if not stats:
            return 0.0
        return stats[0].success_rate

    def get_avg_duration(self, provider_id: str, task_type: TaskType) -> Optional[float]:
        stats = self.get_stats(provider_id=provider_id, task_type=task_type)
        if not stats:
            return None
        return stats[0].avg_duration_ms

    @property
    def total_records(self) -> int:
        return len(self._records)
