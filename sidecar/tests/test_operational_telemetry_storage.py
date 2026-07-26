import pytest

from sentinel.contracts import HealthStateV1
from sentinel.operational_telemetry_hub import (
    OperationalEventFactory,
    OperationalTelemetryHub,
    TelemetryIntegrityError,
)


def _event(event_type="POLICY_DECISION"):
    return OperationalEventFactory.synthetic(
        correlation_id="correlation-1",
        evidence_hash="b" * 64,
        issuer_id="issuer.telemetry.v1",
        event_type=event_type,
        health_state=HealthStateV1.HEALTHY,
        decision_state="MATCH",
    )


def test_disabled_hub_creates_no_database(tmp_path):
    path = tmp_path / "telemetry.sqlite3"
    hub = OperationalTelemetryHub(database_path=path, environ={})

    assert hub.enabled is False
    assert hub.storage is None
    assert hub.authority is False
    assert hub.execution_requested is False
    assert not path.exists()


def test_event_and_metrics_persist_after_restart(tmp_path):
    path = tmp_path / "telemetry.sqlite3"
    event = _event()
    hub = OperationalTelemetryHub(database_path=path, enabled=True)
    snapshot = hub.aggregator.ingest(event)
    assert snapshot.decisions == 1
    hub.close()

    reopened = OperationalTelemetryHub(database_path=path, enabled=True)
    assert reopened.storage.read_event(event.event_id) == event
    assert reopened.timeline.latest() == (event,)
    rows = reopened.storage.connection.execute("SELECT COUNT(*) FROM metric_snapshots").fetchone()
    assert rows[0] == 1
    reopened.close()


def test_modified_persisted_event_is_rejected(tmp_path):
    hub = OperationalTelemetryHub(
        database_path=tmp_path / "telemetry.sqlite3",
        enabled=True,
    )
    event = _event()
    hub.storage.write_event(event)
    hub.storage.connection.execute(
        "UPDATE operational_events SET decision_state = ? WHERE event_id = ?",
        ("FAILED", event.event_id),
    )

    with pytest.raises(TelemetryIntegrityError):
        hub.storage.read_event(event.event_id)
    hub.close()
