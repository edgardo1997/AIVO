"""Stable routing error tests."""

from sentinel.core.model_errors import RoutingError, RoutingErrorCode


def test_routing_error_safe_response():
    err = RoutingError(
        code=RoutingErrorCode.MODEL_CLOUD_NOT_AUTHORIZED,
        safe_message="Cloud not authorized for this model.",
        retryable=False,
        recommended_action="request_cloud_authorization",
    )
    payload = err.to_safe_dict(correlation_id="abc-123")
    assert payload["error_code"] == RoutingErrorCode.MODEL_CLOUD_NOT_AUTHORIZED
    assert payload["correlation_id"] == "abc-123"
    assert payload["retryable"] is False
    assert "api_key" not in payload["safe_message"].lower()
