from sentinel.runtime_v2_controlled import (
    RuntimeV2ActivationState,
    RuntimeV2Control,
)
from sentinel.runtime_v2_controlled.control import (
    RUNTIME_V2_ROUTING_ENABLED,
    V2_COMPARISON_ENABLED,
    V2_DIAGNOSTIC_MODE,
)


def test_runtime_v2_flags_default_disabled(monkeypatch):
    for name in (
        "RUNTIME_V2_ROUTING_ENABLED",
        "V2_COMPARISON_ENABLED",
        "V2_DIAGNOSTIC_MODE",
    ):
        monkeypatch.delenv(name, raising=False)
    assert RUNTIME_V2_ROUTING_ENABLED is False
    assert V2_COMPARISON_ENABLED is False
    assert V2_DIAGNOSTIC_MODE is False
    control = RuntimeV2Control.from_environment()
    assert control.state is RuntimeV2ActivationState.DISABLED


def test_runtime_v2_control_states():
    assert RuntimeV2Control(routing_enabled=True).state is RuntimeV2ActivationState.SHADOW_ONLY
    assert (
        RuntimeV2Control(
            routing_enabled=True,
            comparison_enabled=True,
        ).state
        is RuntimeV2ActivationState.COMPARISON_ENABLED
    )
    assert (
        RuntimeV2Control(
            routing_enabled=False,
            comparison_enabled=True,
        ).state
        is RuntimeV2ActivationState.DISABLED
    )
    assert "EXECUTION" not in {state.value for state in RuntimeV2ActivationState}
