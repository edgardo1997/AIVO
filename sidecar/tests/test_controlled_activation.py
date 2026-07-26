from sentinel.controlled_runtime_activation import (
    CONTROLLED_RUNTIME_ACTIVATION_ENABLED,
    MAX_V2_TRAFFIC_PERCENTAGE,
    V2_CANARY_ENABLED,
    V2_TRAFFIC_PERCENTAGE,
    ActivationState,
    ControlledActivationControl,
    ControlledRuntimeActivation,
)


def test_flags_are_off_and_traffic_is_zero() -> None:
    assert CONTROLLED_RUNTIME_ACTIVATION_ENABLED is False
    assert V2_CANARY_ENABLED is False
    assert V2_TRAFFIC_PERCENTAGE == 0
    assert MAX_V2_TRAFFIC_PERCENTAGE == 5
    activation = ControlledRuntimeActivation(ControlledActivationControl(environ={}))
    assert activation.state is ActivationState.DISABLED
    assert not activation.start()


def test_legacy_remains_default_when_canary_is_not_enabled() -> None:
    activation = ControlledRuntimeActivation(
        ControlledActivationControl(
            enabled=True,
            canary_enabled=False,
            traffic_percentage=0,
        )
    )
    assert activation.state is ActivationState.LEGACY_ONLY
    assert not activation.start()
    assert activation.state is ActivationState.LEGACY_ONLY


def test_activation_states_pause_and_resume() -> None:
    activation = ControlledRuntimeActivation(
        ControlledActivationControl(
            enabled=True,
            canary_enabled=True,
            traffic_percentage=1,
        )
    )
    assert activation.start()
    assert activation.state is ActivationState.CANARY_ACTIVE
    activation.pause()
    assert activation.state is ActivationState.PAUSED
    assert activation.resume()
    assert activation.state is ActivationState.CANARY_ACTIVE
