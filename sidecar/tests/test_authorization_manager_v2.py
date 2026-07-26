from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from sentinel.authorization_manager import (
    AuthorizationManagerControl,
    AuthorizationManagerV2,
)
from sentinel.authorization_manager.validation import (
    AuthorizationValidationError,
)
from sentinel.contracts import (
    AuthorizationScopeV1,
    AuthorizationStatusV1,
    ConsentDecisionValueV1,
    EvidenceIntegrityStatusV1,
    PolicyEvaluationStatusV1,
)
from sentinel.operational_telemetry_hub import OperationalTelemetryHub
from test_consent_manager_v2 import (
    _manager as _consent_manager,
    _request as _consent_request,
    _signed_policy_inputs,
)


def _granted_inputs(tmp_path):
    values, policy, verifier = _signed_policy_inputs(tmp_path)
    consent_manager, consent_telemetry = _consent_manager(
        tmp_path / "consent",
        verifier,
    )
    pending = _consent_request(consent_manager, values, policy).consent
    granted = consent_manager.decide(
        pending.consent_id,
        decision=ConsentDecisionValueV1.CONSENT_GRANTED,
        decision_source="human:reviewer",
        now=pending.timestamp + timedelta(minutes=1),
    ).consent
    consent_telemetry.close()
    return values, policy, granted, verifier


def _manager(tmp_path, verifier, *, enabled=True):
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "authorization.sqlite3",
        enabled=True,
    )
    manager = AuthorizationManagerV2(
        control=AuthorizationManagerControl(enabled=enabled),
        verifier=verifier,
        telemetry_hub=telemetry,
    )
    return manager, telemetry


def _request(manager, values, policy, consent):
    now = consent.timestamp + timedelta(minutes=1)
    return manager.request(
        consent=consent,
        policy=policy,
        evidence=values["evidence"],
        scope=AuthorizationScopeV1.USER_APPROVED_ACTION,
        expires_at=now + timedelta(minutes=3),
        now=now,
    )


def test_valid_consent_creates_pending_not_authorized_grant(tmp_path):
    values, policy, consent, verifier = _granted_inputs(tmp_path)
    manager, telemetry = _manager(tmp_path, verifier)
    try:
        operation = _request(manager, values, policy, consent)
        grant = operation.grant
        assert grant.status is AuthorizationStatusV1.AUTH_PENDING
        assert grant.consent_id == consent.consent_id
        assert grant.scope is AuthorizationScopeV1.USER_APPROVED_ACTION
        assert grant.authority is False
        assert grant.execution_requested is False
        with pytest.raises(PermissionError, match="AUTHORIZED_LIMITED"):
            grant.assert_usable(at=grant.created_at)
    finally:
        telemetry.close()


def test_limited_authorization_requires_second_explicit_human_step(tmp_path):
    values, policy, consent, verifier = _granted_inputs(tmp_path)
    manager, telemetry = _manager(tmp_path, verifier)
    try:
        pending = _request(manager, values, policy, consent).grant
        with pytest.raises(AuthorizationValidationError, match="human actor"):
            manager.authorize_limited(
                pending.grant_id,
                actor="authorization-manager",
            )
        limited = manager.authorize_limited(
            pending.grant_id,
            actor="human:reviewer",
            now=pending.created_at + timedelta(seconds=1),
        ).grant
        assert limited.status is AuthorizationStatusV1.AUTHORIZED_LIMITED
        assert limited.authority is False
        assert limited.execution_requested is False
    finally:
        telemetry.close()


def test_blocked_policy_rejects_authorization_evaluation(tmp_path):
    values, policy, consent, verifier = _granted_inputs(tmp_path)
    manager, telemetry = _manager(tmp_path, verifier)
    blocked = policy.model_copy(update={"policy_status": PolicyEvaluationStatusV1.POLICY_BLOCKED})
    try:
        with pytest.raises(AuthorizationValidationError, match="blocked policy"):
            _request(manager, values, blocked, consent)
    finally:
        telemetry.close()


def test_invalid_evidence_and_wrong_issuer_are_rejected(tmp_path):
    values, policy, consent, verifier = _granted_inputs(tmp_path)
    manager, telemetry = _manager(tmp_path, verifier)
    try:
        invalid_values = dict(values)
        invalid_values["evidence"] = values["evidence"].model_copy(
            update={
                "integrity_status": EvidenceIntegrityStatusV1.INVALID,
            }
        )
        with pytest.raises(
            AuthorizationValidationError,
            match="not verified",
        ):
            _request(manager, invalid_values, policy, consent)

        wrong_issuer = consent.model_copy(update={"issuer_id": "other.issuer"})
        with pytest.raises(AuthorizationValidationError, match="issuer mismatch"):
            _request(manager, values, policy, wrong_issuer)
    finally:
        telemetry.close()


def test_expiration_transitions_to_expired(tmp_path):
    values, policy, consent, verifier = _granted_inputs(tmp_path)
    manager, telemetry = _manager(tmp_path, verifier)
    try:
        pending = _request(manager, values, policy, consent).grant
        expired = manager.get(
            pending.grant_id,
            now=pending.expires_at + timedelta(seconds=1),
        ).grant
        assert expired.status is AuthorizationStatusV1.AUTH_EXPIRED
    finally:
        telemetry.close()


def test_manual_revocation_records_reason_actor_and_audit(tmp_path):
    values, policy, consent, verifier = _granted_inputs(tmp_path)
    manager, telemetry = _manager(tmp_path, verifier)
    try:
        pending = _request(manager, values, policy, consent).grant
        limited = manager.authorize_limited(
            pending.grant_id,
            actor="human:reviewer",
            now=pending.created_at + timedelta(seconds=1),
        ).grant
        operation = manager.revoke(
            limited.grant_id,
            actor="human:reviewer",
            reason="USER_REQUEST",
            now=limited.created_at + timedelta(seconds=2),
        )
        assert operation.grant.status is AuthorizationStatusV1.AUTH_REVOKED
        assert operation.grant.revoked is True
        record = manager.revocation_record(limited.grant_id)
        assert record.reason == "USER_REQUEST"
        assert record.actor == "human:reviewer"
        assert operation.audit_event.result == "AUTH_REVOKED"
    finally:
        telemetry.close()


def test_scopes_are_limited_and_contract_is_immutable(tmp_path):
    values, policy, consent, verifier = _granted_inputs(tmp_path)
    manager, telemetry = _manager(tmp_path, verifier)
    try:
        with pytest.raises(ValueError, match="scope"):
            manager.request(
                consent=consent,
                policy=policy,
                evidence=values["evidence"],
                scope="SYSTEM_CONTROL",
                expires_at=consent.timestamp + timedelta(minutes=2),
                now=consent.timestamp + timedelta(minutes=1),
            )
        grant = _request(manager, values, policy, consent).grant
        with pytest.raises(ValidationError):
            grant.scope = AuthorizationScopeV1.READ_ONLY
        with pytest.raises(ValidationError, match="grant_hash"):
            grant.__class__.model_validate(
                {
                    **grant.model_dump(),
                    "scope": AuthorizationScopeV1.READ_ONLY,
                }
            )
    finally:
        telemetry.close()


def test_authorization_transitions_are_recorded_in_telemetry(tmp_path):
    values, policy, consent, verifier = _granted_inputs(tmp_path)
    manager, telemetry = _manager(tmp_path, verifier)
    try:
        pending_operation = _request(manager, values, policy, consent)
        limited_operation = manager.authorize_limited(
            pending_operation.grant.grant_id,
            actor="human:reviewer",
            now=pending_operation.grant.created_at + timedelta(seconds=1),
        )
        assert telemetry.timeline.latest() == (
            pending_operation.operational_event,
            limited_operation.operational_event,
        )
        assert limited_operation.telemetry_snapshot is not None
    finally:
        telemetry.close()


def test_manager_is_disabled_by_default(tmp_path):
    values, policy, consent, verifier = _granted_inputs(tmp_path)
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "disabled.sqlite3",
        enabled=False,
    )
    manager = AuthorizationManagerV2(
        control=AuthorizationManagerControl(environ={}),
        verifier=verifier,
        telemetry_hub=telemetry,
    )
    now = datetime(2026, 1, 1, 0, 3, tzinfo=UTC)
    assert (
        manager.request(
            consent=consent,
            policy=policy,
            evidence=values["evidence"],
            scope=AuthorizationScopeV1.READ_ONLY,
            expires_at=now + timedelta(minutes=1),
            now=now,
        )
        is None
    )
    assert not (tmp_path / "disabled.sqlite3").exists()
