"""Security and validation tests for PendingConsentV1."""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from sentinel.adapters import pending_action_to_v1
from sentinel.contracts import (
    AuthorizationGrantV1,
    PendingConsentStatusV1,
    PendingConsentV1,
)
from sentinel.core.operational_memory import PendingActionRecord


def _pending(**overrides) -> PendingConsentV1:
    created_at = datetime.now(timezone.utc)
    values = {
        "schema_version": "1.0",
        "pending_consent_id": "pending_notepad",
        "intent_id": "intent_notepad",
        "plan_id": "plan_notepad",
        "step_id": "launch",
        "tool_id": "executor.launch",
        "user_id": "user_local",
        "risk_level": "medium",
        "params_hash": "a" * 64,
        "created_at": created_at,
        "expires_at": created_at + timedelta(minutes=5),
        "status": PendingConsentStatusV1.PENDING,
    }
    values.update(overrides)
    return PendingConsentV1.model_validate(values)


def _legacy_pending() -> PendingActionRecord:
    return PendingActionRecord(
        action_id="pending_notepad",
        tool_id="executor.launch",
        params={"app_name": "Notepad"},
        reason="Consent required",
        created_at=datetime.now(timezone.utc).isoformat(),
        ttl_seconds=600,
        risk_level="medium",
        plan_id="plan_notepad",
        params_hash="legacy-short-hash",
        identity_hash="legacy-identity",
        redacted=True,
    )


def test_pending_consent_creation_and_adapter():
    pending = _pending()
    converted = pending_action_to_v1(
        _legacy_pending(),
        intent_id="intent_notepad",
        step_id="launch",
        user_id="user_local",
    )

    assert pending.status is PendingConsentStatusV1.PENDING
    assert converted.pending_consent_id == "pending_notepad"
    assert converted.plan_id == "plan_notepad"
    assert converted.params_hash != "legacy-short-hash"
    assert len(converted.params_hash) == 64


def test_pending_consent_rejects_invalid_expiration():
    created_at = datetime.now(timezone.utc)

    with pytest.raises(ValidationError, match="later than created_at"):
        _pending(
            created_at=created_at,
            expires_at=created_at,
        )


def test_pending_consent_rejects_invalid_status():
    with pytest.raises(ValidationError, match="PENDING"):
        _pending(status="EXECUTING")


def test_pending_consent_is_not_authorization_grant():
    pending = _pending()

    assert not isinstance(pending, AuthorizationGrantV1)
    assert not hasattr(pending, "authorized_steps")
    assert not hasattr(pending, "grant_hash")
    assert not hasattr(pending, "execute")
    assert not hasattr(pending, "authorize")
    with pytest.raises(ValidationError):
        AuthorizationGrantV1.model_validate(pending.model_dump())


def test_pending_action_cannot_convert_directly_to_authorization_grant():
    legacy = _legacy_pending()

    with pytest.raises(ValidationError):
        AuthorizationGrantV1.model_validate(asdict(legacy))


def test_pending_consent_requires_hash_and_rejects_unknown_fields():
    payload = _pending().model_dump()
    payload.pop("params_hash")
    with pytest.raises(ValidationError, match="Field required"):
        PendingConsentV1.model_validate(payload)

    payload = _pending().model_dump()
    payload["execute"] = True
    with pytest.raises(ValidationError, match="Extra inputs"):
        PendingConsentV1.model_validate(payload)
