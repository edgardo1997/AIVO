"""Explicit coordination of persistence and aggregate metrics."""

from .events import OperationalEventV1
from .metrics import OperationalMetricAggregator, OperationalMetricSnapshotV1
from .storage import OperationalTelemetryStorage


class OperationalTelemetryAggregator:
    def __init__(
        self,
        *,
        storage: OperationalTelemetryStorage,
        metrics: OperationalMetricAggregator | None = None,
    ) -> None:
        self.storage = storage
        self.metrics = metrics or OperationalMetricAggregator()

    def ingest(self, event: OperationalEventV1) -> OperationalMetricSnapshotV1:
        self.storage.write_event(event)
        self.metrics.record(event)
        snapshot = self.metrics.snapshot()
        self.storage.write_snapshot(snapshot)
        return snapshot
