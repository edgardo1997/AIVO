"""Passive Tool Gateway V2 evaluation coordinator."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sentinel.contracts import (
    AuditEventV1,
    AuthorizationGrantV1,
    ConsentDecisionResultV1,
    DecisionResultV1,
    EvidenceIntegrityStatusV1,
    EvidenceSignalV1,
    PolicyEvaluationResultV1,
    ToolGatewayDecisionResultV1,
)
from sentinel.evidence_integrity import EvidenceVerifier
from sentinel.operational_telemetry_hub import (
    OperationalEventV1,
    OperationalMetricSnapshotV1,
    OperationalTelemetryHub,
)

from .audit import gateway_events
from .catalog import VerifiedToolCatalog, builtin_verified_catalog
from .control import ToolGatewayControl
from .decision import decide
from .metrics import ToolGatewayMetricSnapshotV1, ToolGatewayMetrics
from .request import ToolRequestV1
from .validation import catalog_violations, origin_violations


class ToolGatewayEvaluationEnvelopeV1(DecisionResultV1):
    decision: ToolGatewayDecisionResultV1
    reason_codes: tuple[str, ...]
    audit_event: AuditEventV1
    operational_event: OperationalEventV1
    telemetry_snapshot: OperationalMetricSnapshotV1 | None
    metrics: ToolGatewayMetricSnapshotV1
    telemetry_error: str | None = None


class PassiveToolGatewayV2:
    """Evaluates a sanitized category and never invokes a tool."""

    authority = False
    execution_requested = False

    def __init__(
        self,
        *,
        control: ToolGatewayControl,
        verifier: EvidenceVerifier,
        telemetry_hub: OperationalTelemetryHub,
        catalog: VerifiedToolCatalog | None = None,
        metrics: ToolGatewayMetrics | None = None,
    ) -> None:
        self.control = control
        self.verifier = verifier
        self.telemetry_hub = telemetry_hub
        self.catalog = catalog or builtin_verified_catalog()
        self.metrics = metrics or ToolGatewayMetrics()

    def evaluate(
        self,
        *,
        request: ToolRequestV1,
        grant: AuthorizationGrantV1,
        consent: ConsentDecisionResultV1,
        evidence: EvidenceSignalV1,
        policy: PolicyEvaluationResultV1,
        now: datetime | None = None,
    ) -> ToolGatewayEvaluationEnvelopeV1 | None:
        if not self.control.enabled:
            return None
        timestamp = now or datetime.now(UTC)
        origin_errors = origin_violations(
            request=request,
            grant=grant,
            consent=consent,
            evidence=evidence,
            policy=policy,
            verifier=self.verifier,
            now=timestamp,
        )
        origin_errors += catalog_violations(
            request=request,
            catalog=self.catalog,
        )
        selected, reason_codes = decide(
            request=request,
            granted_scope=grant.scope,
            risk=policy.risk_level,
            policy_status=policy.policy_status,
            origin_errors=origin_errors,
        )
        decision_id = _decision_id(
            request=request,
            selected=selected.value,
            reasons=reason_codes,
        )
        result = ToolGatewayDecisionResultV1(
            decision_id=decision_id,
            correlation_id=request.correlation_id,
            evidence_hash=request.evidence_hash,
            issuer_id=request.issuer_id,
            authorization_reference=request.authorization_reference,
            plan_id=request.plan_id,
            step_id=request.step_id,
            tool_id=request.tool_id,
            tool_version=request.tool_version,
            params_hash=request.params_hash,
            catalog_hash=self.catalog.catalog.catalog_hash,
            requested_tool_category=request.requested_tool_category,
            scope=request.requested_scope,
            risk_level=policy.risk_level,
            decision=selected,
            confidence=0.0 if origin_errors else policy.confidence,
            timestamp=request.timestamp,
        )
        audit_event, operational_event = gateway_events(
            result,
            integrity_status=(EvidenceIntegrityStatusV1.INVALID if origin_errors else evidence.integrity_status),
        )
        telemetry_snapshot, telemetry_error = self._record_telemetry(operational_event)
        self.metrics.record(selected, invalid_origin=bool(origin_errors))
        return ToolGatewayEvaluationEnvelopeV1(
            decision=result,
            reason_codes=reason_codes,
            audit_event=audit_event,
            operational_event=operational_event,
            telemetry_snapshot=telemetry_snapshot,
            metrics=self.metrics.snapshot(),
            telemetry_error=telemetry_error,
        )

    def _record_telemetry(
        self,
        event: OperationalEventV1,
    ) -> tuple[OperationalMetricSnapshotV1 | None, str | None]:
        aggregator = self.telemetry_hub.aggregator
        storage = self.telemetry_hub.storage
        if aggregator is None or storage is None:
            return None, "TELEMETRY_DISABLED"
        try:
            existing = storage.read_event(event.event_id)
            if existing is not None:
                if existing != event:
                    return None, "TELEMETRY_CONFLICT"
                return aggregator.metrics.snapshot(), None
            return aggregator.ingest(event), None
        except Exception as exc:
            return None, type(exc).__name__


def _decision_id(
    *,
    request: ToolRequestV1,
    selected: str,
    reasons: tuple[str, ...],
) -> str:
    canonical = ":".join(
        (
            request.request_id,
            request.authorization_reference,
            request.requested_tool_category.value,
            request.tool_id,
            request.tool_version,
            request.plan_id,
            request.step_id,
            request.params_hash,
            request.requested_scope.value,
            selected,
            ",".join(reasons),
        )
    )
    return f"gateway:{hashlib.sha256(canonical.encode()).hexdigest()[:32]}"
