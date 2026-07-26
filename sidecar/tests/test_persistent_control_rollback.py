import pytest

from sentinel.persistent_control_boundary import (
    InvalidTransitionError,
    PersistentControlBoundary,
    PersistentControlState,
)

EVIDENCE_HASH = "e" * 64
ISSUER_ID = "issuer.boundary.v1"
SIGNATURE = "s" * 88


def _selected_boundary(tmp_path):
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
    boundary.transaction.transition(
        correlation_id="request-1",
        evidence_hash=EVIDENCE_HASH,
        issuer_id=ISSUER_ID,
        signature=SIGNATURE,
        target=PersistentControlState.CANARY_SELECTED,
        activation_state="CANARY_SELECTED",
    )
    return boundary


def test_canary_selection_can_be_rolled_back_idempotently(tmp_path):
    boundary = _selected_boundary(tmp_path)
    first = boundary.rollback.rollback(
        correlation_id="request-1",
        evidence_hash=EVIDENCE_HASH,
        issuer_id=ISSUER_ID,
        signature=SIGNATURE,
    )
    second = boundary.rollback.rollback(
        correlation_id="request-1",
        evidence_hash=EVIDENCE_HASH,
        issuer_id=ISSUER_ID,
        signature=SIGNATURE,
    )

    assert first.state is PersistentControlState.ROLLED_BACK
    assert second.state is PersistentControlState.ROLLED_BACK
    assert second.activation_state == "INACTIVE"
    assert second.rollback_state == "ROLLBACK_RECORDED"
    boundary.close()


def test_rollback_before_canary_selection_is_rejected(tmp_path):
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

    with pytest.raises(InvalidTransitionError):
        boundary.rollback.rollback(
            correlation_id="request-1",
            evidence_hash=EVIDENCE_HASH,
            issuer_id=ISSUER_ID,
            signature=SIGNATURE,
        )
    boundary.close()
