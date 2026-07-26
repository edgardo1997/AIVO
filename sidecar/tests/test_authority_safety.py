from sentinel.authority_safety_layer import (
    AUTHORITY_SAFETY_LAYER_ENABLED,
    AuthoritySafetyControl,
    AuthoritySafetyController,
    AuthoritySafetyStorage,
    IdempotencyState,
)


def test_disabled_by_default_creates_no_storage(tmp_path) -> None:
    database = tmp_path / "disabled.db"
    assert AUTHORITY_SAFETY_LAYER_ENABLED is False
    controller = AuthoritySafetyController(
        control=AuthoritySafetyControl(environ={}),
        database_path=database,
    )
    assert controller.storage is None
    assert controller.idempotency is None
    assert controller.authority is False
    assert not database.exists()


def test_state_persists_across_reopen(tmp_path) -> None:
    database = tmp_path / "safety.db"
    controller = AuthoritySafetyController(
        control=AuthoritySafetyControl(enabled=True),
        database_path=database,
    )
    record = controller.idempotency.begin(
        correlation_id="corr_1",
        migration_state="LIMITED_CANARY",
        fallback_state="NOT_REQUIRED",
        authority_decision="V2_LIMITED",
        evidence_hash="a" * 64,
        ttl_seconds=60,
    )
    assert record.state is IdempotencyState.PENDING
    controller.idempotency.transition("corr_1", IdempotencyState.COMMITTED)
    controller.close()

    reopened = AuthoritySafetyStorage(database)
    persisted = reopened.get("corr_1")
    assert persisted is not None
    assert persisted.state is IdempotencyState.COMMITTED
    assert persisted.authority is False
    reopened.close()


def test_persistent_audit_stores_only_safe_metadata(tmp_path) -> None:
    controller = AuthoritySafetyController(
        control=AuthoritySafetyControl(enabled=True),
        database_path=tmp_path / "audit.db",
    )
    controller.audit.append(
        event="AUTHORITY_SELECTED",
        evidence_hash="b" * 64,
        result="RECORDED",
    )
    assert controller.audit.count() == 1
    controller.close()
