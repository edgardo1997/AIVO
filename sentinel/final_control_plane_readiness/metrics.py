"""Aggregate-only final readiness metrics."""

from dataclasses import dataclass
from threading import RLock

from .decision import FinalReadinessStatus


@dataclass(frozen=True)
class FinalReadinessMetricsSnapshot:
    total_evaluations: int
    blocked_count: int
    review_count: int
    failed_gate_count: int


class FinalReadinessMetrics:
    def __init__(self) -> None:
        self._lock = RLock()
        self._evaluations = 0
        self._blocked = 0
        self._reviews = 0
        self._failed_gates = 0

    def record(
        self,
        *,
        status: FinalReadinessStatus,
        failed_gates: int,
    ) -> None:
        with self._lock:
            self._evaluations += 1
            self._blocked += int(status is FinalReadinessStatus.BLOCKED)
            self._reviews += int(
                status
                in {
                    FinalReadinessStatus.READY_FOR_HUMAN_REVIEW,
                    FinalReadinessStatus.HIGH_CONFIDENCE_REVIEW,
                }
            )
            self._failed_gates += max(0, failed_gates)

    def snapshot(self) -> FinalReadinessMetricsSnapshot:
        with self._lock:
            return FinalReadinessMetricsSnapshot(
                total_evaluations=self._evaluations,
                blocked_count=self._blocked,
                review_count=self._reviews,
                failed_gate_count=self._failed_gates,
            )
