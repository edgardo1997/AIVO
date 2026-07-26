"""Aggregate in-memory execution counters."""

from dataclasses import dataclass

from sentinel.contracts import LimitedExecutionStatusV1


@dataclass(frozen=True)
class LimitedExecutionMetricsSnapshotV1:
    total: int
    succeeded: int
    failed: int
    timed_out: int
    blocked: int
    fallback_required: int


class LimitedExecutionMetrics:
    def __init__(self) -> None:
        self._counts = {status: 0 for status in LimitedExecutionStatusV1}

    def record(self, status: LimitedExecutionStatusV1) -> None:
        self._counts[status] += 1

    def snapshot(self) -> LimitedExecutionMetricsSnapshotV1:
        return LimitedExecutionMetricsSnapshotV1(
            total=sum(self._counts.values()),
            succeeded=self._counts[LimitedExecutionStatusV1.SUCCEEDED],
            failed=self._counts[LimitedExecutionStatusV1.FAILED],
            timed_out=self._counts[LimitedExecutionStatusV1.TIMED_OUT],
            blocked=self._counts[LimitedExecutionStatusV1.BLOCKED],
            fallback_required=self._counts[LimitedExecutionStatusV1.FALLBACK_REQUIRED],
        )
