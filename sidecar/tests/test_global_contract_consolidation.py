import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from sentinel.activation_gateway.audit import GatewayAuditEvent
from sentinel.canary_environment.health import CanaryHealthStatus
from sentinel.contracts import (
    AuditEventV1,
    DecisionResultV1,
    HealthStateV1,
    HealthStatusV1,
    ReadinessResultV1,
    ReadinessStateValueV1,
)
from sentinel.controlled_runtime_activation.audit import ActivationAuditEvent
from sentinel.controlled_runtime_activation.health import ActivationHealthStatus
from sentinel.decision_long_term_evaluation.health import (
    DecisionLongTermHealthStatus,
)
from sentinel.final_control_plane_readiness.decision import (
    FinalReadinessDecision,
    FinalReadinessStatus,
)
from sentinel.runtime_trial.health import RuntimeTrialHealthStatus
from sentinel.v2_authority_migration.audit import AuthorityAuditEvent
from sentinel.v2_authority_readiness.readiness import AuthorityReadinessState
from sentinel.v2_authority_readiness.validator import (
    AuthorityReadinessResultV1,
)
from sentinel.v2_operational_observability.health import OperationalHealthStatus
from sentinel.v2_operational_observability.timeline import (
    OperationalTimelineEvent,
)

ROOT = Path(__file__).parents[2]
PACKAGES = (
    "canary_environment",
    "runtime_trial",
    "decision_shadow_validation",
    "decision_long_term_evaluation",
    "v2_authority_readiness",
    "v2_authority_migration",
    "authority_safety_layer",
    "runtime_equivalence_validation",
    "activation_gateway",
    "controlled_runtime_activation",
    "v2_operational_observability",
    "v2_operational_evidence_storage",
    "v2_trust_evaluation",
    "final_control_plane_readiness",
    "persistent_control_boundary",
)
FORBIDDEN_IMPORTS = {
    "executor_service",
    "tool_gateway",
    "orchestrator",
    "core.planner",
    "core.policy_engine",
    "core.decision_engine",
    "subprocess",
}


def test_all_health_vocabularies_are_the_central_enum():
    aliases = (
        CanaryHealthStatus,
        RuntimeTrialHealthStatus,
        DecisionLongTermHealthStatus,
        ActivationHealthStatus,
        OperationalHealthStatus,
    )
    assert all(alias is HealthStateV1 for alias in aliases)
    assert set(HealthStateV1) == {
        HealthStateV1.HEALTHY,
        HealthStateV1.OBSERVING,
        HealthStateV1.WARNING,
        HealthStateV1.DEGRADED,
        HealthStateV1.CRITICAL,
    }


def test_health_contract_is_immutable_and_non_authoritative():
    health = HealthStatusV1(state=HealthStateV1.OBSERVING)
    assert health.authority is False
    assert health.execution_requested is False
    with pytest.raises(ValidationError):
        health.state = HealthStateV1.HEALTHY


def test_readiness_consumers_share_the_central_contract():
    assert AuthorityReadinessState is ReadinessStateValueV1
    assert FinalReadinessStatus is ReadinessStateValueV1
    assert issubclass(AuthorityReadinessResultV1, ReadinessResultV1)
    assert issubclass(FinalReadinessDecision, ReadinessResultV1)
    assert issubclass(ReadinessResultV1, DecisionResultV1)


def test_audit_consumers_share_the_central_contract():
    aliases = (
        GatewayAuditEvent,
        ActivationAuditEvent,
        AuthorityAuditEvent,
        OperationalTimelineEvent,
    )
    assert all(alias is AuditEventV1 for alias in aliases)
    assert set(AuditEventV1.model_fields) == {
        "authority",
        "execution_requested",
        "event_id",
        "event_type",
        "timestamp",
        "correlation_id",
        "evidence_hash",
        "issuer_id",
        "result",
    }


def test_global_v2_contract_boundaries_have_no_aliases_or_runtime_imports():
    for package in PACKAGES:
        for path in (ROOT / "sentinel" / package).glob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert "action_requested" not in source
            assert "authority_explicit" not in source
            tree = ast.parse(source)
            imports = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names
            }
            assert not any(forbidden in imported for imported in imports for forbidden in FORBIDDEN_IMPORTS)


def test_central_decisions_reject_authority_and_execution():
    with pytest.raises(ValidationError):
        ReadinessResultV1(
            status=ReadinessStateValueV1.BLOCKED,
            confidence=0,
            evidence_hash="a" * 64,
            correlation_id="readiness-1",
            authority=True,
        )
    with pytest.raises(ValidationError):
        ReadinessResultV1(
            status=ReadinessStateValueV1.BLOCKED,
            confidence=0,
            evidence_hash="a" * 64,
            correlation_id="readiness-1",
            execution_requested=True,
        )
