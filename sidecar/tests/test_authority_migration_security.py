import pytest

from sentinel.v2_authority_migration import (
    AuthorityAuditLog,
    AuthorityMigrationMetrics,
    AuthorityMigrationReport,
    AuthorityMigrationState,
    AuthoritySelection,
    MigrationPolicyV1,
)


def test_policy_rejects_broad_traffic_and_unsanitized_scope() -> None:
    with pytest.raises(ValueError):
        MigrationPolicyV1(
            allowed_operations=("safe.operation",),
            traffic_percentage=100,
            fallback_conditions=("FAIL",),
            maximum_trial_seconds=60,
            rollback_criteria=("FAIL",),
        )
    with pytest.raises(ValueError):
        MigrationPolicyV1(
            allowed_operations=("C:\\private\\command",),
            traffic_percentage=1,
            fallback_conditions=("FAIL",),
            maximum_trial_seconds=60,
            rollback_criteria=("FAIL",),
        )


def test_audit_accepts_only_sanitized_transition_codes() -> None:
    audit = AuthorityAuditLog()
    audit.record(
        transition_type="CANARY_START",
        state="LIMITED_CANARY",
        result="ACCEPTED",
    )
    event = audit.snapshot()[0]
    assert event.timestamp.utcoffset() is not None
    assert not hasattr(event, "user")
    assert not hasattr(event, "command")
    with pytest.raises(ValueError):
        audit.record(
            transition_type="prompt with secret",
            state="FAILED",
            result="REJECTED",
        )


def test_aggregate_metrics_and_report() -> None:
    metrics = AuthorityMigrationMetrics()
    metrics.record(AuthoritySelection.LEGACY_AUTHORITY)
    metrics.record(AuthoritySelection.V2_AUTHORITY)
    metrics.record(AuthoritySelection.FALLBACK_LEGACY)
    metrics.record_rollback()
    snapshot = metrics.snapshot()
    assert snapshot.routing_decisions == 3
    assert snapshot.legacy_selections == 1
    assert snapshot.v2_selections == 1
    assert snapshot.fallbacks == 1
    assert snapshot.rollbacks == 1
    assert not hasattr(metrics, "operations")
    report = AuthorityMigrationReport(
        state=AuthorityMigrationState.ROLLBACK,
        metrics=snapshot,
        risks=("V2_FAILURE",),
        recommendation="KEEP_LEGACY_AUTHORITY",
    )
    assert report.human_readable().startswith("SENTINEL CONTROLLED V2 AUTHORITY MIGRATION REPORT")
