"""Extremely limited, opt-in V2 execution service."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Callable, Mapping

from sentinel.contracts import (
    ApplicationDescriptorV1,
    AuditEventV1,
    AuthorizationGrantV1,
    EvidenceIntegrityStatusV1,
    EvidenceSignalV1,
    HealthStateV1,
    LimitedExecutionReceiptV1,
    LimitedExecutionStatusV1,
    LaunchReceiptV1,
    LaunchStateV1,
    ToolGatewayDecisionResultV1,
)
from sentinel.evidence_integrity import EvidenceVerifier
from sentinel.operational_telemetry_hub import (
    OperationalEventV1,
    OperationalTelemetryHub,
)

from .backend import LimitedExecutionBackend
from .control import LimitedExecutionControl
from .metrics import LimitedExecutionMetrics
from .models import LimitedExecutionRequestV1, LimitedOperationV1
from .validation import validate_execution


class LimitedExecutionV2:
    """Executes only three catalog-bound operations after full authorization."""

    authority = False

    def __init__(
        self,
        *,
        control: LimitedExecutionControl,
        verifier: EvidenceVerifier,
        consume_grant: Callable[..., object],
        telemetry_hub: OperationalTelemetryHub,
        backend: LimitedExecutionBackend,
        resource_catalog: Mapping[str, Path] | None = None,
        metrics: LimitedExecutionMetrics | None = None,
    ) -> None:
        self.control = control
        self.verifier = verifier
        self.consume_grant = consume_grant
        self.telemetry_hub = telemetry_hub
        self.backend = backend
        self.resource_catalog = dict(resource_catalog or {})
        self.metrics = metrics or LimitedExecutionMetrics()
        self._consumed_authorizations: set[str] = set()

    def execute(
        self,
        *,
        request: LimitedExecutionRequestV1,
        grant: AuthorizationGrantV1,
        gateway: ToolGatewayDecisionResultV1,
        evidence: EvidenceSignalV1,
        descriptor: ApplicationDescriptorV1 | None = None,
        now: datetime | None = None,
    ) -> LimitedExecutionReceiptV1:
        started_at = now or datetime.now(UTC)
        if not self.control.enabled:
            return self._receipt(
                request,
                status=LimitedExecutionStatusV1.BLOCKED,
                started_at=started_at,
                completed_at=started_at,
                result_code="EXECUTION_DISABLED",
                rollback_state="NOT_REQUIRED",
                fallback_available=True,
            )
        errors = validate_execution(
            request=request,
            grant=grant,
            gateway=gateway,
            evidence=evidence,
            verifier=self.verifier,
            descriptor=descriptor,
            now=started_at,
        )
        if errors:
            return self._receipt(
                request,
                status=LimitedExecutionStatusV1.BLOCKED,
                started_at=started_at,
                completed_at=started_at,
                result_code=errors[0],
                rollback_state="NOT_REQUIRED",
                fallback_available=True,
            )
        if grant.authorization_id in self._consumed_authorizations:
            return self._receipt(
                request,
                status=LimitedExecutionStatusV1.BLOCKED,
                started_at=started_at,
                completed_at=started_at,
                result_code="AUTHORIZATION_REPLAYED",
                rollback_state="NOT_REQUIRED",
                fallback_available=True,
            )
        self.consume_grant(
            grant.grant_id,
            params_hash=request.params_hash,
            now=started_at,
        )
        self._consumed_authorizations.add(grant.authorization_id)
        timer = monotonic()
        try:
            result = self._dispatch(request, descriptor)
            elapsed = monotonic() - timer
            completed_at = datetime.now(UTC)
            if elapsed > self.control.timeout_seconds:
                return self._receipt(
                    request,
                    status=LimitedExecutionStatusV1.TIMED_OUT,
                    started_at=started_at,
                    completed_at=completed_at,
                    result_code="EXECUTION_TIMEOUT",
                    rollback_state="LOGICAL_ONLY",
                    fallback_available=True,
                )
            return self._receipt(
                request,
                status=LimitedExecutionStatusV1.SUCCEEDED,
                started_at=started_at,
                completed_at=completed_at,
                result_code="EXECUTION_SUCCEEDED",
                sanitized_result=result,
                application_receipt=(
                    LaunchReceiptV1(
                        schema_version="1.0",
                        receipt_id=f"launch:{request.request_id}",
                        authorization_id=request.authorization_id,
                        plan_id=request.plan_id,
                        step_id=request.step_id,
                        application_id=request.application_id,
                        state=LaunchStateV1.LAUNCH_REQUESTED,
                        pid=(int(result["pid"]) if result.get("pid") is not None else None),
                        started_at=started_at,
                        completed_at=completed_at,
                    )
                    if request.operation is LimitedOperationV1.APPLICATION_LAUNCH
                    else None
                ),
                rollback_state="NOT_REQUIRED",
                fallback_available=True,
            )
        except Exception:
            return self._receipt(
                request,
                status=LimitedExecutionStatusV1.FALLBACK_REQUIRED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                result_code="V2_EXECUTION_FAILED",
                rollback_state="FALLBACK_AVAILABLE",
                fallback_available=True,
            )

    def _dispatch(
        self,
        request: LimitedExecutionRequestV1,
        descriptor: ApplicationDescriptorV1 | None,
    ) -> dict[str, object]:
        if request.operation is LimitedOperationV1.SYSTEM_INFORMATION:
            return self.backend.system_information()
        if request.operation is LimitedOperationV1.FILE_METADATA:
            path = self.resource_catalog.get(request.resource_id or "")
            if path is None:
                raise LookupError("resource is not in the trusted catalog")
            return self.backend.file_metadata(path)
        if descriptor is None:
            raise ValueError("verified application descriptor required")
        return self.backend.launch_application(descriptor)

    def _receipt(
        self,
        request: LimitedExecutionRequestV1,
        *,
        status: LimitedExecutionStatusV1,
        started_at: datetime,
        completed_at: datetime,
        result_code: str,
        rollback_state: str,
        fallback_available: bool,
        sanitized_result: dict[str, object] | None = None,
        application_receipt: LaunchReceiptV1 | None = None,
    ) -> LimitedExecutionReceiptV1:
        receipt = LimitedExecutionReceiptV1(
            receipt_id=_receipt_id(request, status),
            correlation_id=request.correlation_id,
            evidence_hash=request.evidence_hash,
            authorization_id=request.authorization_id,
            plan_id=request.plan_id,
            step_id=request.step_id,
            tool_id=request.tool_id,
            params_hash=request.params_hash,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            result_code=result_code,
            sanitized_result=sanitized_result or {},
            rollback_state=rollback_state,
            fallback_available=fallback_available,
            application_receipt=application_receipt,
        )
        self.metrics.record(status)
        self._audit(receipt)
        return receipt

    def _audit(self, receipt: LimitedExecutionReceiptV1) -> None:
        audit = AuditEventV1(
            event_id=f"audit:{receipt.receipt_id}",
            event_type="V2_LIMITED_EXECUTION_COMPLETED",
            timestamp=receipt.completed_at,
            correlation_id=receipt.correlation_id,
            evidence_hash=receipt.evidence_hash,
            issuer_id="sentinel.limited-execution.v2",
            result=receipt.status.value,
        )
        event = OperationalEventV1(
            event_id=f"telemetry:{receipt.receipt_id}",
            correlation_id=receipt.correlation_id,
            evidence_hash=receipt.evidence_hash,
            issuer_id=audit.issuer_id,
            timestamp=receipt.completed_at,
            event_type="V2_LIMITED_EXECUTION_COMPLETED",
            health_state=(
                HealthStateV1.OBSERVING
                if receipt.status is LimitedExecutionStatusV1.SUCCEEDED
                else HealthStateV1.WARNING
            ),
            decision_state=receipt.status.value,
            integrity_status=EvidenceIntegrityStatusV1.VERIFIED,
        )
        if self.telemetry_hub.aggregator is not None:
            self.telemetry_hub.aggregator.ingest(event)


def _receipt_id(
    request: LimitedExecutionRequestV1,
    status: LimitedExecutionStatusV1,
) -> str:
    value = f"{request.request_id}:{request.authorization_id}:{request.params_hash}:{status.value}"
    return f"receipt:{hashlib.sha256(value.encode()).hexdigest()[:32]}"
