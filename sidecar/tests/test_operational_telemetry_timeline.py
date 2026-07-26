from sentinel.contracts import HealthStateV1
from sentinel.operational_telemetry_hub import (
    OperationalEventFactory,
    OperationalTelemetryHub,
)


def _event(index: int):
    return OperationalEventFactory.synthetic(
        correlation_id=f"correlation-{index}",
        evidence_hash=f"{index:064x}",
        issuer_id="issuer.telemetry.v1",
        event_type="CANARY_OBSERVATION",
        health_state=HealthStateV1.HEALTHY,
        decision_state="MATCH",
    )


def test_timeline_is_ordered_and_bounded(tmp_path):
    hub = OperationalTelemetryHub(
        database_path=tmp_path / "telemetry.sqlite3",
        enabled=True,
    )
    events = tuple(_event(index) for index in range(3))
    for event in events:
        hub.storage.write_event(event)

    assert hub.timeline.latest(2) == events[-2:]
    hub.close()


def test_timeline_has_referential_integrity(tmp_path):
    hub = OperationalTelemetryHub(
        database_path=tmp_path / "telemetry.sqlite3",
        enabled=True,
    )
    event = _event(1)
    hub.storage.write_event(event)
    hub.storage.connection.execute(
        "DELETE FROM operational_events WHERE event_id = ?",
        (event.event_id,),
    )
    count = hub.storage.connection.execute("SELECT COUNT(*) FROM timeline_index").fetchone()[0]
    assert count == 0
    hub.close()
