from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from sentinel.contract_adapters import adapt_authority
from sentinel.contracts import NonAuthoritativeDecisionV1


def test_authority_adapter_produces_central_contract():
    result = adapt_authority(
        SimpleNamespace(authority=False, execution_requested=False),
        correlation_id="correlation-1",
    )

    assert isinstance(result.contract, NonAuthoritativeDecisionV1)
    assert result.contract.authority is False
    assert result.contract.execution_requested is False
    assert result.metadata.correlation_id == "correlation-1"
    assert result.metadata.evidence_hash
    assert result.metadata.timestamp.tzinfo is not None


@pytest.mark.parametrize(
    "source",
    [
        {"authority": True},
        {"execution_requested": True},
        {"action_requested": False},
        {"authority_explicit": False},
    ],
)
def test_authority_adapter_rejects_authority_and_aliases(source):
    with pytest.raises(ValueError):
        adapt_authority(source, correlation_id="correlation-1")


def test_adapter_result_is_immutable():
    result = adapt_authority(object(), correlation_id="correlation-1")

    with pytest.raises(FrozenInstanceError):
        result.contract = None
