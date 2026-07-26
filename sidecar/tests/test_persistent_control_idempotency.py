import pytest

from sentinel.persistent_control_boundary import (
    EvidenceConflictError,
    InvalidTransitionError,
    PersistentControlBoundary,
    PersistentControlState,
)

EVIDENCE_HASH = "b" * 64
ISSUER_ID = "issuer.boundary.v1"
SIGNATURE = "s" * 88


def test_repeated_reservation_is_idempotent_across_restart(tmp_path):
    path = tmp_path / "boundary.sqlite3"
    first = PersistentControlBoundary(database_path=path, enabled=True)
    initial = first.idempotency.reserve(
        correlation_id="request-1",
        evidence_hash=EVIDENCE_HASH,
        issuer_id=ISSUER_ID,
        signature=SIGNATURE,
    )
    first.close()

    second = PersistentControlBoundary(database_path=path, enabled=True)
    replay = second.idempotency.reserve(
        correlation_id="request-1",
        evidence_hash=EVIDENCE_HASH,
        issuer_id=ISSUER_ID,
        signature=SIGNATURE,
    )
    assert replay.state is PersistentControlState.RESERVED
    assert replay.created_at == initial.created_at
    second.close()


def test_same_correlation_with_different_evidence_is_rejected(tmp_path):
    boundary = PersistentControlBoundary(
        database_path=tmp_path / "boundary.sqlite3",
        enabled=True,
    )
    boundary.idempotency.reserve(
        correlation_id="request-1",
        evidence_hash=EVIDENCE_HASH,
        issuer_id=ISSUER_ID,
        signature=SIGNATURE,
    )

    with pytest.raises(EvidenceConflictError):
        boundary.idempotency.reserve(
            correlation_id="request-1",
            evidence_hash="c" * 64,
            issuer_id=ISSUER_ID,
            signature=SIGNATURE,
        )
    boundary.close()


def test_same_correlation_rejects_signature_or_issuer_substitution(tmp_path):
    boundary = PersistentControlBoundary(
        database_path=tmp_path / "boundary.sqlite3",
        enabled=True,
    )
    boundary.idempotency.reserve(
        correlation_id="request-1",
        evidence_hash=EVIDENCE_HASH,
        issuer_id=ISSUER_ID,
        signature=SIGNATURE,
    )

    with pytest.raises(EvidenceConflictError):
        boundary.idempotency.reserve(
            correlation_id="request-1",
            evidence_hash=EVIDENCE_HASH,
            issuer_id="issuer.attacker.v1",
            signature="x" * 88,
        )
    boundary.close()


def test_invalid_transition_is_rejected_without_state_change(tmp_path):
    boundary = PersistentControlBoundary(
        database_path=tmp_path / "boundary.sqlite3",
        enabled=True,
    )
    boundary.transaction.create(
        correlation_id="request-1",
        evidence_hash=EVIDENCE_HASH,
        issuer_id=ISSUER_ID,
        signature=SIGNATURE,
    )

    with pytest.raises(InvalidTransitionError):
        boundary.transaction.transition(
            correlation_id="request-1",
            evidence_hash=EVIDENCE_HASH,
            issuer_id=ISSUER_ID,
            signature=SIGNATURE,
            target=PersistentControlState.COMMITTED,
        )
    assert boundary.transaction.get("request-1").state is PersistentControlState.NEW
    boundary.close()
