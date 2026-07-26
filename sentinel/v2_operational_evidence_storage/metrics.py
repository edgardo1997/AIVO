"""Aggregate-only evidence storage metrics."""

from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class EvidenceStorageMetricsSnapshot:
    total_records: int
    integrity_failures: int
    recovery_events: int
    deleted_records: int
    storage_errors: int


class EvidenceStorageMetrics:
    def __init__(self) -> None:
        self._lock = RLock()
        self._values = {
            "total_records": 0,
            "integrity_failures": 0,
            "recovery_events": 0,
            "deleted_records": 0,
            "storage_errors": 0,
        }

    def increment(self, metric: str, amount: int = 1) -> None:
        if metric not in self._values:
            raise ValueError("unknown evidence storage metric")
        with self._lock:
            self._values[metric] += max(0, amount)

    def snapshot(self) -> EvidenceStorageMetricsSnapshot:
        with self._lock:
            return EvidenceStorageMetricsSnapshot(**self._values)
