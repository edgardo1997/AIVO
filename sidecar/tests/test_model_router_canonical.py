"""Canonical ModelRouter request/decision contract tests."""

import pytest
from sentinel.core.model_router import ModelRouter
from sentinel.core.model_schemas import ModelRequest, PrivacyRequirement, SelectionReasonCode


def test_route_defaults_to_local():
    router = ModelRouter()
    req = ModelRequest(task_type="quick", required_capabilities=["chat"])
    dec = router.route(req)
    assert dec.selected_provider == "sentinel_local"
    assert dec.selection_reason_code == SelectionReasonCode.LOCAL_CAPABLE_PREFERRED
    assert dec.cloud_used is False


def test_route_local_only_rejects_cloud():
    router = ModelRouter()
    req = ModelRequest(task_type="quick", privacy_requirement=PrivacyRequirement.LOCAL_ONLY, cloud_allowed=True)
    dec = router.route(req)
    assert dec.cloud_used is False


def test_route_explanation_does_not_leak_internal_data():
    router = ModelRouter()
    req = ModelRequest(task_type="quick")
    dec = router.route(req)
    assert dec.safe_explanation
    assert "api_key" not in dec.safe_explanation.lower()


def test_execute_requires_known_provider():
    router = ModelRouter()
    req = ModelRequest(task_type="quick", provider_preference="nonexistent")
    with pytest.raises(ValueError):
        router.execute(req, [{"role": "user", "content": "hi"}])
