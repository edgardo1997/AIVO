from sentinel.persistent_control_boundary import (
    PERSISTENT_CONTROL_BOUNDARY_ENABLED,
    PersistentControlBoundary,
    PersistentControlState,
)

EVIDENCE_HASH = "a" * 64
ISSUER_ID = "issuer.boundary.v1"
SIGNATURE = "s" * 88


def test_boundary_is_disabled_by_default_and_creates_no_database(tmp_path):
    database_path = tmp_path / "boundary.sqlite3"
    boundary = PersistentControlBoundary(
        database_path=database_path,
        environ={},
    )

    assert PERSISTENT_CONTROL_BOUNDARY_ENABLED is False
    assert boundary.enabled is False
    assert boundary.storage is None
    assert boundary.authority is False
    assert boundary.execution_requested is False
    assert not database_path.exists()


def test_explicit_state_machine_is_persistent(tmp_path):
    database_path = tmp_path / "boundary.sqlite3"
    boundary = PersistentControlBoundary(
        database_path=database_path,
        enabled=True,
    )
    record = boundary.transaction.create(
        correlation_id="request-1",
        evidence_hash=EVIDENCE_HASH,
        issuer_id=ISSUER_ID,
        signature=SIGNATURE,
    )
    assert record.state is PersistentControlState.NEW
    record = boundary.transaction.transition(
        correlation_id="request-1",
        evidence_hash=EVIDENCE_HASH,
        issuer_id=ISSUER_ID,
        signature=SIGNATURE,
        target=PersistentControlState.PENDING_VALIDATION,
    )
    assert record.state is PersistentControlState.PENDING_VALIDATION
    boundary.close()

    reopened = PersistentControlBoundary(
        database_path=database_path,
        enabled=True,
    )
    persisted = reopened.transaction.get("request-1")
    assert persisted is not None
    assert persisted.state is PersistentControlState.PENDING_VALIDATION
    assert persisted.authority is False
    assert persisted.execution_requested is False
    reopened.close()


def test_full_canary_state_path_commits(tmp_path):
    boundary = PersistentControlBoundary(
        database_path=tmp_path / "boundary.sqlite3",
        enabled=True,
    )
    record = boundary.idempotency.reserve(
        correlation_id="request-2",
        evidence_hash=EVIDENCE_HASH,
        issuer_id=ISSUER_ID,
        signature=SIGNATURE,
    )
    assert record.state is PersistentControlState.RESERVED
    record = boundary.transaction.transition(
        correlation_id="request-2",
        evidence_hash=EVIDENCE_HASH,
        issuer_id=ISSUER_ID,
        signature=SIGNATURE,
        target=PersistentControlState.CANARY_SELECTED,
        activation_state="CANARY_SELECTED",
    )
    record = boundary.transaction.transition(
        correlation_id="request-2",
        evidence_hash=EVIDENCE_HASH,
        issuer_id=ISSUER_ID,
        signature=SIGNATURE,
        target=PersistentControlState.COMMITTED,
    )
    assert record.state is PersistentControlState.COMMITTED
    boundary.close()
