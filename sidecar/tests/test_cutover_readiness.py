from datetime import datetime, timezone

from sentinel.core.intent import Intent
from sentinel.core.operational_memory import PendingActionRecord
from sentinel.core.policy import PolicyEffect, PolicyResult
from sentinel.shadow import (
    CutoverReadinessState,
    CutoverReadinessValidator,
    ShadowMigrationObserver,
)


def test_cutover_readiness_is_ready_with_available_contracts():
    report = CutoverReadinessValidator().validate()
    assert report.state is CutoverReadinessState.READY
    assert all(report.checks.values())
    assert report.blockers == ()


def test_cutover_readiness_blocks_on_critical_shadow_gap():
    observer = ShadowMigrationObserver()
    observer.observe_pending_action(
        PendingActionRecord(
            action_id="pending",
            tool_id="executor.launch",
            params={},
            reason="Consent",
            created_at=datetime.now(timezone.utc).isoformat(),
            ttl_seconds=60,
            plan_id="plan_x",
        )
    )
    report = CutoverReadinessValidator().validate(observer)
    assert report.state is CutoverReadinessState.BLOCKED
    assert report.blockers
    assert report.checks["shadow_observer_no_critical_errors"] is False


def test_cutover_readiness_warns_on_noncritical_shadow_warning():
    observer = ShadowMigrationObserver()
    observer.observe_policy(
        PolicyResult(
            effect=PolicyEffect.ALLOW,
            policy_id="system.read",
            reason="Allowed",
        ),
        plan_id="plan_x",
    )
    report = CutoverReadinessValidator().validate(observer)
    assert report.state is CutoverReadinessState.WARNING
    assert report.blockers == ()
    assert report.warnings


def test_cutover_readiness_handles_clean_shadow_observer():
    observer = ShadowMigrationObserver()
    observer.observe(
        Intent(
            action="query",
            target="system.info",
            raw_input="Ver sistema",
        )
    )
    report = CutoverReadinessValidator().validate(observer)
    assert report.state is CutoverReadinessState.READY
