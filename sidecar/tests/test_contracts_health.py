import pytest
from pydantic import ValidationError

from sentinel.contracts import (
    HealthStateV1,
    HealthStatusV1,
    ReadinessStateV1,
    ReadinessStateValueV1,
)


@pytest.mark.parametrize("state", list(HealthStateV1))
def test_health_states_are_supported(state):
    result = HealthStatusV1(state=state)

    assert result.state is state
    assert result.authority is False
    assert result.execution_requested is False


def test_unknown_health_state_is_rejected():
    with pytest.raises(ValidationError):
        HealthStatusV1(state="EXECUTING")


@pytest.mark.parametrize("state", list(ReadinessStateValueV1))
def test_readiness_states_are_non_authoritative(state):
    result = ReadinessStateV1(state=state)

    assert result.state is state
    assert result.authority is False
    assert result.execution_requested is False


def test_readiness_contract_is_immutable():
    result = ReadinessStateV1(state=ReadinessStateValueV1.BLOCKED)

    with pytest.raises(ValidationError):
        result.state = ReadinessStateValueV1.READY_FOR_HUMAN_REVIEW
