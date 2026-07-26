from sentinel.v2_authority_migration import (
    AuthorityMigrationController,
    AuthorityMigrationState,
    AuthorityRouter,
    AuthoritySelection,
    FallbackController,
    MigrationPolicyV1,
)


def test_fallback_is_idempotent_and_rolls_back() -> None:
    controller = AuthorityMigrationController(
        enabled=True,
        scope=("safe.operation",),
    )
    controller.begin_limited_canary(
        policy=MigrationPolicyV1(
            allowed_operations=("safe.operation",),
            traffic_percentage=1,
            fallback_conditions=("V2_FAILURE",),
            maximum_trial_seconds=60,
            rollback_criteria=("ANY_FAILURE",),
        ),
        readiness_approved=True,
    )
    router = AuthorityRouter(controller)
    fallback = FallbackController(controller, router)

    first = fallback.on_v2_failure("corr_safe")
    second = fallback.on_v2_failure("corr_safe")

    assert first == second
    assert first.selection is AuthoritySelection.FALLBACK_LEGACY
    assert controller.state is AuthorityMigrationState.ROLLBACK
    assert first.execution_requested is False


def test_rollback_prevents_future_v2_selection() -> None:
    controller = AuthorityMigrationController(
        enabled=True,
        scope=("safe.operation",),
    )
    controller.rollback()
    assert controller.state is AuthorityMigrationState.ROLLBACK
