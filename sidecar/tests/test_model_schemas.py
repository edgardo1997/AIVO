"""Canonical model routing schema tests."""

import pytest
from sentinel.core.model_schemas import (
    CapabilityStatus,
    EmbeddingRequest,
    FallbackPolicy,
    ModelCapability,
    ModelRequest,
    PrivacyRequirement,
    RoutingDecision,
    SelectionReasonCode,
)


def test_model_request_defaults_to_cloud_not_allowed():
    req = ModelRequest(task_type="chat")
    assert req.cloud_allowed is False
    assert req.fallback_policy == FallbackPolicy.NONE


def test_model_request_local_only_enforces_flags():
    req = ModelRequest(privacy_requirement=PrivacyRequirement.LOCAL_ONLY)
    assert req.local_only is True
    assert req.cloud_allowed is False


def test_model_request_rejects_unknown_fields():
    with pytest.raises(ValueError):
        ModelRequest(invalid_field="x")


def test_model_request_reason_codes_from_enum():
    dec = RoutingDecision(selection_reason_code=SelectionReasonCode.LOCAL_CAPABLE_PREFERRED)
    assert dec.selection_reason_code == SelectionReasonCode.LOCAL_CAPABLE_PREFERRED


def test_capability_unknown_not_verified():
    cap = ModelCapability(name="vision", status=CapabilityStatus.UNKNOWN)
    assert cap.status == CapabilityStatus.UNKNOWN


def test_embedding_request_defaults_local_only():
    req = EmbeddingRequest(texts=["hello"])
    assert req.local_only is True
    assert req.cloud_allowed is False
