"""Human-only consent lifecycle with no execution authority."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

from sentinel.contracts import (
    AuditEventV1,
    ConsentDecisionResultV1,
    ConsentDecisionValueV1,
    DecisionResultV1,
    EvidenceSignalV1,
    PolicyEvaluationResultV1,
    ReadinessResultV1,
    SimulationResultV1,
)
from sentinel.evidence_integrity import EvidenceVerifier
from sentinel.operational_telemetry_hub import (
    OperationalEventV1,
    OperationalMetricSnapshotV1,
    OperationalTelemetryHub,
)
from sentinel.recommendation_engine import RecommendationResultV1

from .audit import consent_events
from .control import ConsentManagerControl
from .expiration import is_expired
from .metrics import ConsentMetricSnapshotV1, ConsentMetrics
from .revocation import ConsentRevocationRecordV1
from .validation import ConsentValidationError, validate_consent_request

_SAFE_REASON = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


class ConsentOperationResultV1(DecisionResultV1):
    consent: ConsentDecisionResultV1
    audit_event: AuditEventV1
    operational_event: OperationalEventV1
    telemetry_snapshot: OperationalMetricSnapshotV1 | None
    metrics: ConsentMetricSnapshotV1
    telemetry_error: str | None = None


class ConsentManagerV2:
    """Records explicit human consent without creating a permission grant."""

    authority = False
    execution_requested = False

    def __init__(
        self,
        *,
        control: ConsentManagerControl,
        verifier: EvidenceVerifier,
        telemetry_hub: OperationalTelemetryHub,
        metrics: ConsentMetrics | None = None,
    ) -> None:
        self.control = control
        self.verifier = verifier
        self.telemetry_hub = telemetry_hub
        self.metrics = metrics or ConsentMetrics()
        self._consents: dict[str, ConsentDecisionResultV1] = {}
        self._revocations: dict[str, ConsentRevocationRecordV1] = {}

    def request(
        self,
        *,
        policy: PolicyEvaluationResultV1,
        simulation: SimulationResultV1,
        recommendation: RecommendationResultV1,
        evidence: EvidenceSignalV1,
        readiness: ReadinessResultV1,
        expiration_time: datetime,
        now: datetime | None = None,
    ) -> ConsentOperationResultV1 | None:
        if not self.control.enabled:
            return None
        validate_consent_request(
            policy=policy,
            simulation=simulation,
            recommendation=recommendation,
            evidence=evidence,
            readiness=readiness,
            verifier=self.verifier,
        )
        timestamp = now or datetime.now(UTC)
        consent_id = _consent_id(
            correlation_id=evidence.correlation_id,
            evidence_hash=evidence.payload_hash,
            request_type=simulation.action_type.value,
        )
        existing = self._consents.get(consent_id)
        if existing is not None:
            return self._record(self._expire_if_needed(existing, timestamp))
        consent = ConsentDecisionResultV1(
            consent_id=consent_id,
            correlation_id=evidence.correlation_id,
            evidence_hash=evidence.payload_hash,
            issuer_id=evidence.issuer_id,
            timestamp=timestamp,
            request_type=simulation.action_type,
            decision=ConsentDecisionValueV1.CONSENT_PENDING,
            decision_source="consent-manager",
            expiration_time=expiration_time,
            revoked=False,
            confidence=min(
                policy.confidence,
                simulation.confidence,
                recommendation.evaluation.confidence,
                readiness.confidence,
            ),
        )
        self._consents[consent_id] = consent
        return self._record(consent)

    def decide(
        self,
        consent_id: str,
        *,
        decision: ConsentDecisionValueV1,
        decision_source: str,
        now: datetime | None = None,
    ) -> ConsentOperationResultV1:
        if not self.control.enabled:
            raise ConsentValidationError("consent manager is disabled")
        if decision not in {
            ConsentDecisionValueV1.CONSENT_GRANTED,
            ConsentDecisionValueV1.CONSENT_DENIED,
        }:
            raise ConsentValidationError("only explicit grant or denial is a human decision")
        timestamp = now or datetime.now(UTC)
        current = self._required(consent_id)
        current = self._expire_if_needed(current, timestamp)
        if current.decision is ConsentDecisionValueV1.CONSENT_EXPIRED:
            return self._record(current)
        if current.decision is not ConsentDecisionValueV1.CONSENT_PENDING:
            raise ConsentValidationError("consent is no longer pending")
        updated = current.model_copy(
            update={
                "timestamp": timestamp,
                "decision": decision,
                "decision_source": decision_source,
            }
        )
        updated = ConsentDecisionResultV1.model_validate(updated.model_dump())
        self._consents[consent_id] = updated
        return self._record(updated)

    def get(
        self,
        consent_id: str,
        *,
        now: datetime | None = None,
    ) -> ConsentOperationResultV1:
        if not self.control.enabled:
            raise ConsentValidationError("consent manager is disabled")
        current = self._required(consent_id)
        updated = self._expire_if_needed(current, now or datetime.now(UTC))
        return self._record(updated)

    def revoke(
        self,
        consent_id: str,
        *,
        decision_source: str,
        reason: str,
        now: datetime | None = None,
    ) -> ConsentOperationResultV1:
        if not self.control.enabled:
            raise ConsentValidationError("consent manager is disabled")
        if not _SAFE_REASON.fullmatch(reason):
            raise ConsentValidationError("revocation reason must be a safe code")
        timestamp = now or datetime.now(UTC)
        current = self._expire_if_needed(
            self._required(consent_id),
            timestamp,
        )
        if current.decision is not ConsentDecisionValueV1.CONSENT_GRANTED:
            raise ConsentValidationError("only granted consent can be revoked")
        revoked = current.model_copy(
            update={
                "timestamp": timestamp,
                "decision": ConsentDecisionValueV1.CONSENT_REVOKED,
                "decision_source": decision_source,
                "revoked": True,
            }
        )
        revoked = ConsentDecisionResultV1.model_validate(revoked.model_dump())
        self._consents[consent_id] = revoked
        self._revocations[consent_id] = ConsentRevocationRecordV1(
            consent_id=consent_id,
            correlation_id=revoked.correlation_id,
            reason=reason,
            timestamp=timestamp,
            decision_source=decision_source,
        )
        return self._record(revoked)

    def revocation_record(
        self,
        consent_id: str,
    ) -> ConsentRevocationRecordV1 | None:
        return self._revocations.get(consent_id)

    def _expire_if_needed(
        self,
        consent: ConsentDecisionResultV1,
        now: datetime,
    ) -> ConsentDecisionResultV1:
        if consent.decision in {
            ConsentDecisionValueV1.CONSENT_DENIED,
            ConsentDecisionValueV1.CONSENT_EXPIRED,
            ConsentDecisionValueV1.CONSENT_REVOKED,
        }:
            return consent
        if not is_expired(consent, now=now):
            return consent
        expired = consent.model_copy(
            update={
                "timestamp": now,
                "decision": ConsentDecisionValueV1.CONSENT_EXPIRED,
                "decision_source": "consent-manager",
            }
        )
        expired = ConsentDecisionResultV1.model_validate(expired.model_dump())
        self._consents[consent.consent_id] = expired
        return expired

    def _required(self, consent_id: str) -> ConsentDecisionResultV1:
        try:
            return self._consents[consent_id]
        except KeyError as exc:
            raise ConsentValidationError("consent record not found") from exc

    def _record(
        self,
        consent: ConsentDecisionResultV1,
    ) -> ConsentOperationResultV1:
        audit_event, operational_event = consent_events(consent)
        telemetry_snapshot = None
        telemetry_error = None
        aggregator = self.telemetry_hub.aggregator
        storage = self.telemetry_hub.storage
        if aggregator is None or storage is None:
            telemetry_error = "TELEMETRY_DISABLED"
        else:
            try:
                existing = storage.read_event(operational_event.event_id)
                if existing is None:
                    telemetry_snapshot = aggregator.ingest(operational_event)
                elif existing == operational_event:
                    telemetry_snapshot = aggregator.metrics.snapshot()
                else:
                    telemetry_error = "TELEMETRY_CONFLICT"
            except Exception as exc:
                telemetry_error = type(exc).__name__
        self.metrics.record(consent.decision)
        return ConsentOperationResultV1(
            consent=consent,
            audit_event=audit_event,
            operational_event=operational_event,
            telemetry_snapshot=telemetry_snapshot,
            metrics=self.metrics.snapshot(),
            telemetry_error=telemetry_error,
        )


def _consent_id(
    *,
    correlation_id: str,
    evidence_hash: str,
    request_type: str,
) -> str:
    digest = hashlib.sha256(f"{correlation_id}:{evidence_hash}:{request_type}".encode("utf-8")).hexdigest()
    return f"consent:{digest[:32]}"
