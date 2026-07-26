from datetime import datetime, timezone

from sentinel.core.intent import Intent
from sentinel.core.operational_memory import PendingActionRecord
from sentinel.core.policy import PolicyEffect, PolicyResult
from sentinel.shadow import ShadowMigrationObserver


def _valid_intent():
    return Intent(
        action="query",
        target="system.info",
        raw_input="Ver sistema",
    )


def test_shadow_metrics_increment_correctly():
    observer = ShadowMigrationObserver()
    observer.observe(_valid_intent())
    observer.observe_policy(
        PolicyResult(
            effect=PolicyEffect.ALLOW,
            policy_id="system.read",
            reason="Allowed",
        ),
        plan_id="plan_x",
    )
    metrics = observer.metrics()
    assert metrics.conversion_success == 2
    assert metrics.conversion_failure == 0
    assert metrics.warning_count >= 1
    assert metrics.component_count == {"intent": 1, "policy": 1}


def test_shadow_metrics_are_isolated_between_observers():
    first = ShadowMigrationObserver()
    second = ShadowMigrationObserver()
    first.observe(_valid_intent())
    assert first.metrics().conversion_success == 1
    assert second.metrics().conversion_success == 0


def test_shadow_errors_increment_failure_without_breaking_observation():
    observer = ShadowMigrationObserver()
    observer.observe(Intent(action="", target="", raw_input=""))
    observer.observe(_valid_intent())
    metrics = observer.metrics()
    assert metrics.conversion_failure == 1
    assert metrics.conversion_success == 1


def test_shadow_metrics_count_missing_contract_and_fields():
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
    metrics = observer.metrics()
    assert metrics.missing_contract == 1
    assert metrics.missing_field == 3
    assert metrics.component_count["consent"] == 1
