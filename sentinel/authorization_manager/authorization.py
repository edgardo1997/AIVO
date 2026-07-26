"""Passive limited-authorization lifecycle after explicit human consent."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime

from sentinel.contracts import (
    AuditEventV1,
    AuthorizationGrantV1,
    AuthorizationScopeV1,
    AuthorizationStatusV1,
    ConsentDecisionResultV1,
    DecisionResultV1,
    EvidenceSignalV1,
    PolicyEvaluationResultV1,
    SimulationActionTypeV1,
)
from sentinel.evidence_integrity import EvidenceVerifier
from sentinel.operational_telemetry_hub import (
    OperationalEventV1,
    OperationalMetricSnapshotV1,
    OperationalTelemetryHub,
)

from .audit import authorization_events
from .control import AuthorizationManagerControl
from .expiration import grant_is_expired
from .metrics import AuthorizationMetricSnapshotV1, AuthorizationMetrics
from .revocation import AuthorizationRevocationRecordV1
from .scope import validate_scope
from .validation import (
    AuthorizationValidationError,
    validate_authorization_inputs,
)

_SAFE_REASON = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


class AuthorizationRequestV1(DecisionResultV1):
    correlation_id: str
    consent_id: str
    evidence_hash: str
    issuer_id: str
    scope: AuthorizationScopeV1
    allowed_action: SimulationActionTypeV1
    created_at: datetime
    expires_at: datetime


class AuthorizationOperationResultV1(DecisionResultV1):
    request: AuthorizationRequestV1 | None = None
    grant: AuthorizationGrantV1
    audit_event: AuditEventV1
    operational_event: OperationalEventV1
    telemetry_snapshot: OperationalMetricSnapshotV1 | None
    metrics: AuthorizationMetricSnapshotV1
    telemetry_error: str | None = None


class AuthorizationManagerV2:
    """Creates passive limited grants with no execution integration."""

    authority = False
    execution_requested = False

    def __init__(
        self,
        *,
        control: AuthorizationManagerControl,
        verifier: EvidenceVerifier,
        telemetry_hub: OperationalTelemetryHub,
        metrics: AuthorizationMetrics | None = None,
    ) -> None:
        self.control = control
        self.verifier = verifier
        self.telemetry_hub = telemetry_hub
        self.metrics = metrics or AuthorizationMetrics()
        self._grants: dict[str, AuthorizationGrantV1] = {}
        self._revocations: dict[str, AuthorizationRevocationRecordV1] = {}
        self._consumed_ids: set[str] = set()

    def request(
        self,
        *,
        consent: ConsentDecisionResultV1,
        policy: PolicyEvaluationResultV1,
        evidence: EvidenceSignalV1,
        scope: AuthorizationScopeV1,
        expires_at: datetime,
        params_hash: str | None = None,
        plan_id: str | None = None,
        step_id: str | None = None,
        tool_id: str = "authorization.passive",
        now: datetime | None = None,
    ) -> AuthorizationOperationResultV1 | None:
        if not self.control.enabled:
            return None
        timestamp = now or datetime.now(UTC)
        validate_scope(scope)
        validate_authorization_inputs(
            consent=consent,
            policy=policy,
            evidence=evidence,
            verifier=self.verifier,
        )
        if timestamp >= consent.expiration_time:
            raise AuthorizationValidationError("human consent has expired")
        if expires_at > consent.expiration_time:
            raise AuthorizationValidationError("grant cannot outlive human consent")
        if expires_at <= timestamp:
            raise AuthorizationValidationError("grant expiration must follow creation")
        grant_id = _grant_id(
            consent_id=consent.consent_id,
            evidence_hash=evidence.payload_hash,
            scope=scope,
        )
        if grant_id in self._consumed_ids:
            raise AuthorizationValidationError("authorization replay detected")
        request = AuthorizationRequestV1(
            correlation_id=evidence.correlation_id,
            consent_id=consent.consent_id,
            evidence_hash=evidence.payload_hash,
            issuer_id=evidence.issuer_id,
            scope=scope,
            allowed_action=consent.request_type,
            created_at=timestamp,
            expires_at=expires_at,
        )
        grant = AuthorizationGrantV1.issue_limited(
            grant_id=grant_id,
            correlation_id=evidence.correlation_id,
            consent_id=consent.consent_id,
            evidence_hash=evidence.payload_hash,
            issuer_id=evidence.issuer_id,
            scope=scope,
            allowed_action=consent.request_type,
            status=AuthorizationStatusV1.AUTH_PENDING,
            policy_decision_id=policy.policy_id,
            decision_source=consent.decision_source,
            created_at=timestamp,
            expires_at=expires_at,
            nonce=f"nonce:{grant_id.split(':', 1)[1]}",
            params_hash=params_hash,
            plan_id=plan_id,
            step_id=step_id,
            tool_id=tool_id,
        )
        self._grants[grant_id] = grant
        return self._record(grant, timestamp=timestamp, request=request)

    def issue_limited_from_consent(
        self,
        *,
        consent: ConsentDecisionResultV1,
        policy: PolicyEvaluationResultV1,
        evidence: EvidenceSignalV1,
        scope: AuthorizationScopeV1,
        params_hash: str,
        expires_at: datetime,
        plan_id: str | None = None,
        step_id: str | None = None,
        tool_id: str = "authorization.passive",
        now: datetime | None = None,
    ) -> AuthorizationOperationResultV1 | None:
        """Issue a limited grant from the single explicit consent evidence."""
        pending = self.request(
            consent=consent,
            policy=policy,
            evidence=evidence,
            scope=scope,
            params_hash=params_hash,
            plan_id=plan_id,
            step_id=step_id,
            tool_id=tool_id,
            expires_at=expires_at,
            now=now,
        )
        if pending is None:
            return None
        grant = self._transition(
            pending.grant,
            status=AuthorizationStatusV1.AUTHORIZED_LIMITED,
        )
        self._grants[grant.grant_id] = grant
        return self._record(grant, timestamp=now or datetime.now(UTC))

    def consume(
        self,
        grant_id: str,
        *,
        params_hash: str,
        now: datetime | None = None,
    ) -> AuthorizationOperationResultV1:
        """Consume once after passive validation; never execute an action."""
        timestamp = now or datetime.now(UTC)
        grant = self._required(grant_id)
        if grant.authorization_id in self._consumed_ids:
            raise AuthorizationValidationError("authorization replay detected")
        if not secrets.compare_digest(grant.params_hash, params_hash):
            raise AuthorizationValidationError("authorization parameter hash mismatch")
        try:
            consumed = grant.mark_consumed(timestamp)
        except PermissionError as exc:
            raise AuthorizationValidationError(str(exc)) from exc
        self._consumed_ids.add(grant.authorization_id)
        self._grants[grant_id] = consumed
        return self._record(consumed, timestamp=timestamp)

    def authorize_limited(
        self,
        grant_id: str,
        *,
        actor: str,
        now: datetime | None = None,
    ) -> AuthorizationOperationResultV1:
        _require_human_actor(actor)
        timestamp = now or datetime.now(UTC)
        grant = self._expire_if_needed(self._required(grant_id), timestamp)
        if grant.status is AuthorizationStatusV1.AUTH_EXPIRED:
            return self._record(grant, timestamp=timestamp)
        if grant.status is not AuthorizationStatusV1.AUTH_PENDING:
            raise AuthorizationValidationError("only pending authorization can become limited")
        updated = self._transition(
            grant,
            status=AuthorizationStatusV1.AUTHORIZED_LIMITED,
        )
        self._grants[grant_id] = updated
        return self._record(updated, timestamp=timestamp)

    def deny(
        self,
        grant_id: str,
        *,
        actor: str,
        now: datetime | None = None,
    ) -> AuthorizationOperationResultV1:
        _require_human_actor(actor)
        timestamp = now or datetime.now(UTC)
        grant = self._expire_if_needed(self._required(grant_id), timestamp)
        if grant.status is not AuthorizationStatusV1.AUTH_PENDING:
            raise AuthorizationValidationError("only pending authorization can be denied")
        updated = self._transition(
            grant,
            status=AuthorizationStatusV1.AUTH_DENIED,
        )
        self._grants[grant_id] = updated
        return self._record(updated, timestamp=timestamp)

    def get(
        self,
        grant_id: str,
        *,
        now: datetime | None = None,
    ) -> AuthorizationOperationResultV1:
        timestamp = now or datetime.now(UTC)
        grant = self._expire_if_needed(self._required(grant_id), timestamp)
        return self._record(grant, timestamp=timestamp)

    def revoke(
        self,
        grant_id: str,
        *,
        actor: str,
        reason: str,
        now: datetime | None = None,
    ) -> AuthorizationOperationResultV1:
        _require_human_actor(actor)
        if not _SAFE_REASON.fullmatch(reason):
            raise AuthorizationValidationError("revocation reason must be a safe code")
        timestamp = now or datetime.now(UTC)
        grant = self._expire_if_needed(self._required(grant_id), timestamp)
        if grant.status is not AuthorizationStatusV1.AUTHORIZED_LIMITED:
            raise AuthorizationValidationError("only limited authorization can be revoked")
        updated = self._transition(
            grant,
            status=AuthorizationStatusV1.AUTH_REVOKED,
            revoked=True,
        )
        self._grants[grant_id] = updated
        self._revocations[grant_id] = AuthorizationRevocationRecordV1(
            grant_id=grant_id,
            correlation_id=grant.correlation_id,
            reason=reason,
            actor=actor,
            timestamp=timestamp,
        )
        return self._record(updated, timestamp=timestamp)

    def revocation_record(
        self,
        grant_id: str,
    ) -> AuthorizationRevocationRecordV1 | None:
        return self._revocations.get(grant_id)

    def _expire_if_needed(
        self,
        grant: AuthorizationGrantV1,
        now: datetime,
    ) -> AuthorizationGrantV1:
        if grant.status in {
            AuthorizationStatusV1.AUTH_EXPIRED,
            AuthorizationStatusV1.AUTH_REVOKED,
            AuthorizationStatusV1.AUTH_DENIED,
        }:
            return grant
        if not grant_is_expired(grant, now=now):
            return grant
        expired = self._transition(
            grant,
            status=AuthorizationStatusV1.AUTH_EXPIRED,
        )
        self._grants[grant.grant_id] = expired
        return expired

    @staticmethod
    def _transition(
        grant: AuthorizationGrantV1,
        *,
        status: AuthorizationStatusV1,
        revoked: bool = False,
    ) -> AuthorizationGrantV1:
        return AuthorizationGrantV1.issue_limited(
            grant_id=grant.grant_id,
            correlation_id=grant.correlation_id,
            consent_id=grant.consent_id,
            evidence_hash=grant.evidence_hash,
            issuer_id=grant.issuer_id,
            scope=grant.scope,
            allowed_action=grant.allowed_action,
            status=status,
            policy_decision_id=grant.policy_decision_id,
            decision_source=grant.user_id,
            created_at=grant.created_at,
            expires_at=grant.expires_at,
            nonce=grant.nonce,
            revoked=revoked,
            params_hash=grant.params_hash,
            plan_id=grant.plan_id,
            step_id=grant.authorized_steps[0].step_id,
            tool_id=grant.authorized_steps[0].tool_id,
        )

    def _required(self, grant_id: str) -> AuthorizationGrantV1:
        try:
            return self._grants[grant_id]
        except KeyError as exc:
            raise AuthorizationValidationError("authorization grant not found") from exc

    def _record(
        self,
        grant: AuthorizationGrantV1,
        *,
        timestamp: datetime,
        request: AuthorizationRequestV1 | None = None,
    ) -> AuthorizationOperationResultV1:
        audit_event, operational_event = authorization_events(
            grant,
            timestamp=timestamp,
        )
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
        self.metrics.record(grant.status)
        return AuthorizationOperationResultV1(
            request=request,
            grant=grant,
            audit_event=audit_event,
            operational_event=operational_event,
            telemetry_snapshot=telemetry_snapshot,
            metrics=self.metrics.snapshot(),
            telemetry_error=telemetry_error,
        )


def _grant_id(
    *,
    consent_id: str,
    evidence_hash: str,
    scope: AuthorizationScopeV1,
) -> str:
    digest = hashlib.sha256(f"{consent_id}:{evidence_hash}:{scope.value}".encode("utf-8")).hexdigest()
    return f"grant:{digest[:32]}"


def _require_human_actor(actor: str) -> None:
    if not actor.startswith("human:"):
        raise AuthorizationValidationError("limited authorization requires an explicit human actor")
