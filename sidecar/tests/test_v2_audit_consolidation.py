from sentinel.activation_gateway.audit import GatewayAuditEvent
from sentinel.authorization_canary.audit import CanaryAuditRecord
from sentinel.contracts import AuditEventV1
from sentinel.controlled_runtime_activation.audit import ActivationAuditEvent
from sentinel.v2_authority_migration.audit import AuthorityAuditEvent
from sentinel.v2_operational_observability.timeline import (
    OperationalTimelineEvent,
)


def test_all_v2_audit_records_use_central_contract():
    aliases = (
        GatewayAuditEvent,
        CanaryAuditRecord,
        ActivationAuditEvent,
        AuthorityAuditEvent,
        OperationalTimelineEvent,
    )
    assert all(alias is AuditEventV1 for alias in aliases)


def test_central_audit_contains_only_sanitized_contract_fields():
    assert set(AuditEventV1.model_fields) == {
        "authority",
        "execution_requested",
        "event_id",
        "correlation_id",
        "evidence_hash",
        "issuer_id",
        "timestamp",
        "event_type",
        "result",
    }
