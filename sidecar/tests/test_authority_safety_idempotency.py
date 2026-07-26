import pytest

from sentinel.authority_safety_layer import (
    AuthoritySafetyStorage,
    IdempotencyState,
    PersistentIdempotencyManager,
)


def manager(tmp_path):
    storage = AuthoritySafetyStorage(tmp_path / "idempotency.db")
    return storage, PersistentIdempotencyManager(storage)


def begin(idempotency, evidence="c"):
    return idempotency.begin(
        correlation_id="corr_safe",
        migration_state="LIMITED_CANARY",
        fallback_state="NOT_REQUIRED",
        authority_decision="V2_LIMITED",
        evidence_hash=evidence * 64,
        ttl_seconds=60,
    )


def test_duplicate_begin_returns_same_persisted_operation(tmp_path) -> None:
    storage, idempotency = manager(tmp_path)
    first = begin(idempotency)
    second = begin(idempotency)
    assert first == second
    assert storage.pending() == (first,)
    storage.close()


def test_evidence_change_is_replay_rejected(tmp_path) -> None:
    storage, idempotency = manager(tmp_path)
    begin(idempotency)
    with pytest.raises(ValueError, match="evidence hash mismatch"):
        begin(idempotency, evidence="d")
    storage.close()


def test_committed_operation_cannot_be_replayed_or_rolled_back(tmp_path) -> None:
    storage, idempotency = manager(tmp_path)
    begin(idempotency)
    committed = idempotency.transition(
        "corr_safe",
        IdempotencyState.COMMITTED,
    )
    assert committed.state is IdempotencyState.COMMITTED
    assert begin(idempotency).state is IdempotencyState.COMMITTED
    with pytest.raises(ValueError, match="invalid idempotency transition"):
        idempotency.transition("corr_safe", IdempotencyState.ROLLED_BACK)
    storage.close()


def test_pending_can_rollback_once(tmp_path) -> None:
    storage, idempotency = manager(tmp_path)
    begin(idempotency)
    rolled_back = idempotency.transition(
        "corr_safe",
        IdempotencyState.ROLLED_BACK,
    )
    assert rolled_back.state is IdempotencyState.ROLLED_BACK
    assert (
        idempotency.transition(
            "corr_safe",
            IdempotencyState.ROLLED_BACK,
        )
        == rolled_back
    )
    storage.close()
