from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError

from sentinel.contracts import DecisionResultV1, NonAuthoritativeDecisionV1


@pytest.mark.parametrize("contract", [NonAuthoritativeDecisionV1, DecisionResultV1])
def test_non_authoritative_defaults_are_false(contract):
    result = contract()

    assert result.authority is False
    assert result.execution_requested is False


@pytest.mark.parametrize("field", ["authority", "execution_requested"])
def test_non_authoritative_fields_cannot_be_true(field):
    with pytest.raises(ValidationError):
        NonAuthoritativeDecisionV1(**{field: True})


@pytest.mark.parametrize("alias", ["action_requested", "authority_explicit"])
def test_dangerous_authority_aliases_are_rejected(alias):
    with pytest.raises(ValidationError):
        NonAuthoritativeDecisionV1(**{alias: False})


def test_non_authoritative_contract_is_immutable():
    result = DecisionResultV1()

    with pytest.raises((ValidationError, FrozenInstanceError)):
        result.authority = False
