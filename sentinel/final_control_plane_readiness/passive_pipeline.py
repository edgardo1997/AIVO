"""Passive contract-to-evidence integration for V2 decisions.

This coordinator has no runtime authority.  It only binds existing contracts,
evidence verification, persistent control, telemetry, and readiness.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Mapping

from pydantic import AfterValidator, Field

from sentinel.contracts import (
    AuditEventV1,
    DecisionResultV1,
    EvidenceIntegrityStatusV1,
    EvidenceSignalV1,
    HealthStateV1,
    ReadinessResultV1,
    ReadinessStateValueV1,
)
from sentinel.contracts._base import FROZEN_MODEL_CONFIG, require_timezone
from sentinel.evidence_integrity import (
    EvidenceSigner,
    EvidenceVerificationStatus,
    EvidenceVerifier,
)
from sentinel.operational_telemetry_hub import (
    OperationalEventV1,
    OperationalMetricSnapshotV1,
    OperationalTelemetryHub,
)
from sentinel.persistent_control_boundary import PersistentControlBoundary

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]
HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
DecisionCode = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")]


class PassivePipelineStatus(str, Enum):
    COMPLETED = "COMPLETED"
    SIGNATURE_REJECTED = "SIGNATURE_REJECTED"
    PERSISTENCE_REJECTED = "PERSISTENCE_REJECTED"
    TELEMETRY_REJECTED = "TELEMETRY_REJECTED"


class ContractBoundDecisionV1(DecisionResultV1):
    """Sanitized decision metadata shared by every derived contract."""

    correlation_id: SafeIdentifier
    evidence_hash: HashValue
    issuer_id: SafeIdentifier
    timestamp: AwareDatetime
    decision_state: DecisionCode


class ContractBoundReadinessResultV1(ReadinessResultV1):
    """Readiness result carrying the same provenance as its decision."""

    issuer_id: SafeIdentifier
    timestamp: AwareDatetime


class PassiveDecisionPipelineResult(DecisionResultV1):
    """Immutable diagnostic result; optional fields expose the stop boundary."""

    model_config = FROZEN_MODEL_CONFIG

    status: PassivePipelineStatus
    correlation_id: SafeIdentifier
    decision: ContractBoundDecisionV1
    evidence: EvidenceSignalV1 | None = None
    audit_event: AuditEventV1 | None = None
    operational_event: OperationalEventV1 | None = None
    readiness: ContractBoundReadinessResultV1 | None = None
    metric_snapshot: OperationalMetricSnapshotV1 | None = None
    error_code: str | None = None


class PassiveV2DecisionPipeline:
    """Fail-closed integration of existing passive V2 boundaries."""

    authority = False
    execution_requested = False

    def __init__(
        self,
        *,
        signer: EvidenceSigner,
        verifier: EvidenceVerifier,
        persistent_boundary: PersistentControlBoundary,
        telemetry_hub: OperationalTelemetryHub,
    ) -> None:
        self.signer = signer
        self.verifier = verifier
        self.persistent_boundary = persistent_boundary
        self.telemetry_hub = telemetry_hub

    def process(
        self,
        *,
        decision_state: str,
        sanitized_request: Mapping[str, object],
        confidence: float,
    ) -> PassiveDecisionPipelineResult:
        correlation_id = f"decision:{uuid.uuid4().hex}"
        timestamp = datetime.now(UTC)
        normalized_state = decision_state.strip().upper()

        try:
            signal = self.signer.sign(
                payload=sanitized_request,
                correlation_id=correlation_id,
                created_at=timestamp,
                evidence_id=f"evidence:{correlation_id.split(':', 1)[1]}",
            )
        except Exception as exc:
            return self._early_failure(
                status=PassivePipelineStatus.SIGNATURE_REJECTED,
                correlation_id=correlation_id,
                timestamp=timestamp,
                issuer_id=self.signer.issuer_id,
                decision_state=normalized_state,
                evidence_hash="0" * 64,
                error_code=type(exc).__name__,
            )

        decision = ContractBoundDecisionV1(
            correlation_id=correlation_id,
            evidence_hash=signal.payload_hash,
            issuer_id=signal.issuer_id,
            timestamp=timestamp,
            decision_state=normalized_state,
        )
        verification = self.verifier.verify(
            signal,
            payload=sanitized_request,
            now=timestamp,
        )
        if verification.status is not EvidenceVerificationStatus.VERIFIED:
            return PassiveDecisionPipelineResult(
                status=PassivePipelineStatus.SIGNATURE_REJECTED,
                correlation_id=correlation_id,
                decision=decision,
                evidence=signal,
                error_code=verification.status.value,
            )
        verified_signal = signal.model_copy(update={"integrity_status": EvidenceIntegrityStatusV1.VERIFIED})

        transaction = self.persistent_boundary.transaction
        if transaction is None:
            return PassiveDecisionPipelineResult(
                status=PassivePipelineStatus.PERSISTENCE_REJECTED,
                correlation_id=correlation_id,
                decision=decision,
                evidence=verified_signal,
                error_code="PERSISTENCE_DISABLED",
            )
        try:
            transaction.create(
                correlation_id=correlation_id,
                evidence_hash=verified_signal.payload_hash,
                issuer_id=verified_signal.issuer_id,
                signature=verified_signal.signature,
            )
        except Exception as exc:
            return PassiveDecisionPipelineResult(
                status=PassivePipelineStatus.PERSISTENCE_REJECTED,
                correlation_id=correlation_id,
                decision=decision,
                evidence=verified_signal,
                error_code=type(exc).__name__,
            )

        audit_event = AuditEventV1(
            event_id=f"audit:{correlation_id.split(':', 1)[1]}",
            event_type="V2_DECISION_PERSISTED",
            timestamp=timestamp,
            correlation_id=correlation_id,
            evidence_hash=verified_signal.payload_hash,
            issuer_id=verified_signal.issuer_id,
            result="PERSISTED",
        )
        operational_event = OperationalEventV1(
            event_id=f"telemetry:{audit_event.event_id}",
            correlation_id=audit_event.correlation_id,
            evidence_hash=audit_event.evidence_hash,
            issuer_id=audit_event.issuer_id,
            timestamp=audit_event.timestamp,
            event_type="V2_DECISION_ACCEPTED",
            health_state=HealthStateV1.HEALTHY,
            decision_state=normalized_state,
            integrity_status=EvidenceIntegrityStatusV1.VERIFIED,
        )
        aggregator = self.telemetry_hub.aggregator
        if aggregator is None:
            return PassiveDecisionPipelineResult(
                status=PassivePipelineStatus.TELEMETRY_REJECTED,
                correlation_id=correlation_id,
                decision=decision,
                evidence=verified_signal,
                audit_event=audit_event,
                operational_event=operational_event,
                error_code="TELEMETRY_DISABLED",
            )
        try:
            snapshot = aggregator.ingest(operational_event)
        except Exception as exc:
            return PassiveDecisionPipelineResult(
                status=PassivePipelineStatus.TELEMETRY_REJECTED,
                correlation_id=correlation_id,
                decision=decision,
                evidence=verified_signal,
                audit_event=audit_event,
                operational_event=operational_event,
                error_code=type(exc).__name__,
            )

        provisional_readiness = ReadinessResultV1(
            status=ReadinessStateValueV1.READY_FOR_HUMAN_REVIEW,
            confidence=confidence,
            evidence_hash=verified_signal.payload_hash,
            correlation_id=verified_signal.correlation_id,
        )
        readiness = self._readiness_from_contracts(
            decision=decision,
            evidence=verified_signal,
            audit_event=audit_event,
            operational_event=operational_event,
            readiness=provisional_readiness,
        )
        return PassiveDecisionPipelineResult(
            status=PassivePipelineStatus.COMPLETED,
            correlation_id=correlation_id,
            decision=decision,
            evidence=verified_signal,
            audit_event=audit_event,
            operational_event=operational_event,
            readiness=readiness,
            metric_snapshot=snapshot,
        )

    @staticmethod
    def _readiness_from_contracts(
        *,
        decision: DecisionResultV1,
        evidence: EvidenceSignalV1,
        audit_event: AuditEventV1,
        operational_event: OperationalEventV1,
        readiness: ReadinessResultV1,
    ) -> ContractBoundReadinessResultV1:
        correlation_ids = {
            getattr(decision, "correlation_id", None),
            evidence.correlation_id,
            audit_event.correlation_id,
            operational_event.correlation_id,
            readiness.correlation_id,
        }
        evidence_hashes = {
            getattr(decision, "evidence_hash", None),
            evidence.payload_hash,
            audit_event.evidence_hash,
            operational_event.evidence_hash,
            readiness.evidence_hash,
        }
        issuer_ids = {
            getattr(decision, "issuer_id", None),
            evidence.issuer_id,
            audit_event.issuer_id,
            operational_event.issuer_id,
        }
        timestamps = {
            getattr(decision, "timestamp", None),
            evidence.created_at,
            audit_event.timestamp,
            operational_event.timestamp,
        }
        if not all(
            len(values) == 1
            for values in (
                correlation_ids,
                evidence_hashes,
                issuer_ids,
                timestamps,
            )
        ):
            raise ValueError("derived contract provenance mismatch")
        return ContractBoundReadinessResultV1(
            status=ReadinessStateValueV1.READY_FOR_HUMAN_REVIEW,
            confidence=readiness.confidence,
            evidence_hash=evidence.payload_hash,
            correlation_id=evidence.correlation_id,
            issuer_id=evidence.issuer_id,
            timestamp=evidence.created_at,
        )

    @staticmethod
    def _early_failure(
        *,
        status: PassivePipelineStatus,
        correlation_id: str,
        timestamp: datetime,
        issuer_id: str,
        decision_state: str,
        evidence_hash: str,
        error_code: str,
    ) -> PassiveDecisionPipelineResult:
        decision = ContractBoundDecisionV1(
            correlation_id=correlation_id,
            evidence_hash=evidence_hash,
            issuer_id=issuer_id,
            timestamp=timestamp,
            decision_state=decision_state,
        )
        return PassiveDecisionPipelineResult(
            status=status,
            correlation_id=correlation_id,
            decision=decision,
            error_code=error_code,
        )
