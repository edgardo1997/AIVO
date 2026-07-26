from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from sentinel.runtime_replay_validation import (
    ReplayComparisonStatus,
    ReplayDatasetV1,
    ReplayMetrics,
)


def test_metrics_are_aggregate_only() -> None:
    metrics = ReplayMetrics()
    metrics.record(
        comparison=ReplayComparisonStatus.MATCH,
        has_errors=False,
        latency_ms=4,
    )
    metrics.record(
        comparison=ReplayComparisonStatus.REGRESSION,
        has_errors=True,
        latency_ms=20,
    )
    metrics.record(
        comparison=ReplayComparisonStatus.NON_DETERMINISTIC,
        has_errors=False,
        latency_ms=80,
    )
    snapshot = metrics.snapshot()

    assert snapshot.processed_events == 3
    assert snapshot.errors == 1
    assert snapshot.matches == 1
    assert snapshot.divergences == 2
    assert snapshot.regressions == 1
    assert snapshot.non_deterministic_results == 1
    assert snapshot.average_latency_ms == pytest.approx(104 / 3)
    assert snapshot.maximum_latency_ms == 80
    assert set(snapshot.latency_percentiles) == {"p50", "p95", "p99"}
    assert not hasattr(metrics, "events")
    assert not hasattr(metrics, "payloads")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_id", r"C:\Users\edgar\secret.txt"),
        ("event_type", "Abrir Notepad"),
        ("sanitized_payload_hash", "not-a-hash"),
    ],
)
def test_dataset_rejects_sensitive_values(field, value) -> None:
    values = {
        "event_id": "safe_event",
        "event_type": "intent_received",
        "version": "1.0",
        "sanitized_payload_hash": "c" * 64,
        "timestamp": datetime.now(timezone.utc),
    }
    values[field] = value
    with pytest.raises(ValidationError):
        ReplayDatasetV1(**values)
