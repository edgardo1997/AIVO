from datetime import datetime, timezone

from sentinel.controlled_runtime_activation import (
    ActivationAudit,
    ActivationMetrics,
    ActivationState,
    CanaryRoutingEvidenceV1,
    ControlledActivationControl,
    ControlledRuntimeActivation,
    ControlledRuntimeRouter,
    RollbackManager,
    RollbackState,
    RuntimeSelection,
)


def setup():
    activation = ControlledRuntimeActivation(
        ControlledActivationControl(
            enabled=True,
            canary_enabled=True,
            traffic_percentage=5,
        )
    )
    activation.start()
    metrics = ActivationMetrics()
    audit = ActivationAudit()
    router = ControlledRuntimeRouter(
        activation=activation,
        metrics=metrics,
        audit=audit,
    )
    rollback = RollbackManager(
        activation=activation,
        router=router,
        metrics=metrics,
        audit=audit,
    )
    return activation, metrics, audit, router, rollback


def test_rollback_changes_only_logical_routing() -> None:
    activation, metrics, audit, _, rollback = setup()
    first = rollback.on_failure("request_failed")
    second = rollback.on_failure("request_failed")
    assert first == second
    assert first.selected_runtime is RuntimeSelection.LEGACY
    assert first.execution_requested is False
    assert activation.state is ActivationState.ROLLBACK_ACTIVE
    assert rollback.state is RollbackState.ROLLBACK_TO_LEGACY
    assert metrics.snapshot().rollbacks == 1
    assert metrics.snapshot().failures == 1
    assert audit.snapshot()[0].event_type == "rollback_triggered"


def test_expired_trial_routes_to_legacy() -> None:
    _, _, _, router, _ = setup()
    result = router.route(
        CanaryRoutingEvidenceV1(
            request_id="expired_request",
            gateway_eligibility="V2_ELIGIBLE_CANARY",
            readiness_approved=True,
            safety_healthy=True,
            rollback_available=True,
            requested_scope="safe.scope",
            allowed_scopes=("safe.scope",),
            trial_started_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            maximum_trial_seconds=1,
            critical_divergences=0,
        )
    )
    assert result.selected_runtime is RuntimeSelection.LEGACY
    assert "TRIAL_EXPIRED" in result.reason_codes
