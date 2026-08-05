"""Adapter contract classification tests."""

from sentinel.core.adapter_contract import AdapterClassification, AdapterContractResult


def test_supported_requires_full_contract():
    result = AdapterContractResult(
        provider="openai",
        checks={k: True for k in [
            "configuration_status", "health", "list_models", "capabilities",
            "non_stream_inference", "stream_inference", "cancel", "connect_timeout",
            "first_token_timeout", "total_timeout", "rate_limit", "auth_failure",
            "malformed_response", "usage_extraction", "cost_extraction",
            "secret_redaction", "tool_call_normalization",
        ]},
        external_validation=True,
    )
    result.classification = AdapterClassification.SUPPORTED if result.pass_rate() == 1.0 and result.external_validation else AdapterClassification.EXPERIMENTAL
    assert result.classification == AdapterClassification.SUPPORTED


def test_partial_contract_is_experimental():
    result = AdapterContractResult(
        provider="mistral",
        checks={"configuration_status": True, "health": True, "list_models": False},
        external_validation=False,
    )
    result.classification = AdapterClassification.EXPERIMENTAL
    assert result.pass_rate() < 1.0
    assert result.classification == AdapterClassification.EXPERIMENTAL


def test_disabled_for_failed_core_check():
    result = AdapterContractResult(
        provider="custom",
        checks={"configuration_status": False, "health": False},
    )
    result.classification = AdapterClassification.DISABLED
    assert result.classification == AdapterClassification.DISABLED
