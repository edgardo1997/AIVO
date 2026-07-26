from datetime import timedelta
import hashlib

import pytest

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
    DecisionResultV1,
    PolicyEvaluationStatusV1,
)
from sentinel.operational_telemetry_hub import OperationalTelemetryHub
from sentinel.v2_unified_pipeline import (
    PassiveUnifiedPipelineV2,
    UnifiedPipelineControl,
    UnifiedPipelineStatusV1,
)
from test_authorization_manager_v2 import _granted_inputs
from test_v2_unified_pipeline import _request

PARAMS_HASH = hashlib.sha256(b'{"mode":"safe"}').hexdigest()


def _manager(tmp_path, verifier):
    hub = OperationalTelemetryHub(
        database_path=tmp_path / "single-authority.sqlite3",
        enabled=True,
    )
    manager = AuthorizationManagerV2(
        control=AuthorizationManagerControl(enabled=True),
        verifier=verifier,
        telemetry_hub=hub,
    )
    return manager, hub


def _issue(manager, values, policy, consent):
    now = consent.timestamp + timedelta(seconds=1)
    return manager.issue_limited_from_consent(
        consent=consent,
        policy=policy,
        evidence=values["evidence"],
        scope=AuthorizationScopeV1.READ_ONLY,
        params_hash=PARAMS_HASH,
        expires_at=now + timedelta(minutes=2),
        now=now,
    )


def test_single_human_consent_issues_limited_grant(tmp_path):
    values, policy, consent, verifier = _granted_inputs(tmp_path)
    manager, hub = _manager(tmp_path, verifier)
    try:
        operation = _issue(manager, values, policy, consent)
        assert operation.grant.status is (AuthorizationStatusV1.AUTHORIZED_LIMITED)
        assert operation.grant.consent_id == consent.consent_id
        assert operation.grant.user_id == consent.decision_source
        assert operation.grant.params_hash == PARAMS_HASH
        assert operation.grant.single_use is True
        assert operation.grant.authority is False
        assert operation.grant.execution_requested is False
    finally:
        hub.close()


def test_policy_is_final_and_blocked_policy_cannot_issue(tmp_path):
    values, policy, consent, verifier = _granted_inputs(tmp_path)
    manager, hub = _manager(tmp_path, verifier)
    blocked = policy.model_copy(update={"policy_status": PolicyEvaluationStatusV1.POLICY_BLOCKED})
    try:
        with pytest.raises(
            AuthorizationValidationError,
            match="blocked policy",
        ):
            _issue(manager, values, blocked, consent)
    finally:
        hub.close()


def test_parameter_change_replay_and_expiration_are_blocked(tmp_path):
    values, policy, consent, verifier = _granted_inputs(tmp_path)
    manager, hub = _manager(tmp_path, verifier)
    try:
        grant = _issue(manager, values, policy, consent).grant
        with pytest.raises(
            AuthorizationValidationError,
            match="parameter hash mismatch",
        ):
            manager.consume(
                grant.grant_id,
                params_hash="0" * 64,
                now=grant.created_at + timedelta(seconds=1),
            )

        consumed = manager.consume(
            grant.grant_id,
            params_hash=PARAMS_HASH,
            now=grant.created_at + timedelta(seconds=1),
        ).grant
        assert consumed.consumed_at is not None
        with pytest.raises(
            AuthorizationValidationError,
            match="replay",
        ):
            manager.consume(
                grant.grant_id,
                params_hash=PARAMS_HASH,
                now=grant.created_at + timedelta(seconds=2),
            )

        second_values, second_policy, second_consent, second_verifier = _granted_inputs(tmp_path / "expired")
        second_manager, second_hub = _manager(
            tmp_path / "expired",
            second_verifier,
        )
        try:
            expired = _issue(
                second_manager,
                second_values,
                second_policy,
                second_consent,
            ).grant
            with pytest.raises(
                AuthorizationValidationError,
                match="expired",
            ):
                second_manager.consume(
                    expired.grant_id,
                    params_hash=PARAMS_HASH,
                    now=expired.expires_at,
                )
        finally:
            second_hub.close()
    finally:
        hub.close()


def test_unified_pipeline_has_no_second_consent_and_blocks_replay(
    tmp_path,
    monkeypatch,
):
    request, verifier = _request(tmp_path)
    hub = OperationalTelemetryHub(
        database_path=tmp_path / "pipeline-authority.sqlite3",
        enabled=True,
    )
    pipeline = PassiveUnifiedPipelineV2(
        control=UnifiedPipelineControl(enabled=True),
        verifier=verifier,
        telemetry_hub=hub,
    )

    def duplicate_human_consent(*args, **kwargs):
        raise AssertionError("duplicate authorization consent invoked")

    monkeypatch.setattr(
        pipeline.authorization_manager,
        "authorize_limited",
        duplicate_human_consent,
    )
    try:
        first = pipeline.evaluate(
            request,
            consent_decision=ConsentDecisionValueV1.CONSENT_GRANTED,
            human_actor="human:reviewer",
        )
        assert first.status is UnifiedPipelineStatusV1.COMPLETED
        assert first.authorization.consumed_at is not None

        replay = pipeline.evaluate(
            request,
            consent_decision=ConsentDecisionValueV1.CONSENT_GRANTED,
            human_actor="human:reviewer",
        )
        assert replay.status is UnifiedPipelineStatusV1.BLOCKED
        assert replay.failed_stage == "authorization"
        assert replay.gateway is None
    finally:
        hub.close()


def test_decision_contract_is_recommendation_only():
    decision = DecisionResultV1()
    assert decision.authority is False
    assert decision.execution_requested is False
    assert not hasattr(decision, "grant")
    assert not hasattr(decision, "authorize")
