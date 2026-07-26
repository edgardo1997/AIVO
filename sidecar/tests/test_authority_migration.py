import hashlib

from sentinel.v2_authority_migration import (
    V2_AUTHORITY_MIGRATION_ENABLED,
    V2_AUTHORITY_SCOPE,
    AuthorityMigrationController,
    AuthorityMigrationState,
    AuthorityRouter,
    AuthoritySelection,
    MigrationPolicyV1,
    RoutingContextV1,
)


def policy() -> MigrationPolicyV1:
    return MigrationPolicyV1(
        allowed_operations=("application.lookup",),
        traffic_percentage=10,
        fallback_conditions=("V2_FAILURE",),
        maximum_trial_seconds=3600,
        rollback_criteria=("CRITICAL_DIVERGENCE",),
    )


def canary_correlation() -> str:
    for index in range(1000):
        value = f"corr_{index}"
        bucket = int(hashlib.sha256(value.encode()).hexdigest()[:8], 16) % 10000
        if bucket < 1000:
            return value
    raise AssertionError("deterministic canary bucket not found")


def context(**updates) -> RoutingContextV1:
    values = {
        "correlation_id": canary_correlation(),
        "operation": "application.lookup",
        "readiness_approved": True,
        "identity_valid": True,
        "policy_context_valid": True,
        "authorization_evidence_valid": True,
        "critical_divergences": 0,
    }
    values.update(updates)
    return RoutingContextV1(**values)


def test_disabled_by_default_routes_to_legacy() -> None:
    assert V2_AUTHORITY_MIGRATION_ENABLED is False
    assert V2_AUTHORITY_SCOPE == ()
    controller = AuthorityMigrationController(environ={})
    assert controller.state is AuthorityMigrationState.DISABLED
    decision = AuthorityRouter(controller).route(context())
    assert decision.selection is AuthoritySelection.LEGACY_AUTHORITY
    assert decision.execution_requested is False


def test_limited_v2_requires_explicit_readiness_and_scope() -> None:
    controller = AuthorityMigrationController(
        enabled=True,
        scope=("application.lookup",),
    )
    assert controller.state is AuthorityMigrationState.SHADOW_ONLY
    assert not controller.begin_limited_canary(
        policy=policy(),
        readiness_approved=False,
    )
    assert controller.begin_limited_canary(
        policy=policy(),
        readiness_approved=True,
    )
    decision = AuthorityRouter(controller).route(context())
    assert decision.selection is AuthoritySelection.V2_AUTHORITY
    assert decision.authority is False
    assert decision.execution_requested is False
    assert not hasattr(decision, "authority_explicit")
    assert decision.execution_requested is False


def test_missing_precondition_keeps_legacy_authority() -> None:
    controller = AuthorityMigrationController(
        enabled=True,
        scope=("application.lookup",),
    )
    controller.begin_limited_canary(
        policy=policy(),
        readiness_approved=True,
    )
    decision = AuthorityRouter(controller).route(context(identity_valid=False))
    assert decision.selection is AuthoritySelection.LEGACY_AUTHORITY


def test_router_is_idempotent_per_correlation() -> None:
    controller = AuthorityMigrationController(
        enabled=True,
        scope=("application.lookup",),
    )
    controller.begin_limited_canary(
        policy=policy(),
        readiness_approved=True,
    )
    router = AuthorityRouter(controller)
    first = router.route(context())
    second = router.route(context(identity_valid=False))
    assert first is second
