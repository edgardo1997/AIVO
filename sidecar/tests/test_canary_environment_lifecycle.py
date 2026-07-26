from sentinel.canary_environment import (
    CanaryEnvironmentControl,
    CanaryEnvironmentLifecycle,
    CanaryEnvironmentState,
)


def lifecycle() -> CanaryEnvironmentLifecycle:
    return CanaryEnvironmentLifecycle(CanaryEnvironmentControl(enabled=True))


def test_complete_lifecycle_is_idempotent() -> None:
    manager = lifecycle()
    created = manager.create(runtime_v2_version="2.0")
    assert created is not None
    assert manager.create(runtime_v2_version="other") is created
    assert manager.start().state is CanaryEnvironmentState.RUNNING
    assert manager.start().state is CanaryEnvironmentState.RUNNING
    assert manager.pause().state is CanaryEnvironmentState.PAUSED
    assert manager.pause().state is CanaryEnvironmentState.PAUSED
    assert manager.resume().state is CanaryEnvironmentState.RUNNING
    assert manager.stop().state is CanaryEnvironmentState.STOPPED
    assert manager.stop().state is CanaryEnvironmentState.STOPPED
    assert len(manager.transitions) == 4


def test_session_recovers_after_pause() -> None:
    manager = lifecycle()
    manager.create(runtime_v2_version="2.0")
    manager.start()
    manager.pause()
    assert manager.create_session(correlation_id="paused") is None
    manager.resume()
    assert manager.create_session(correlation_id="resumed") is not None


def test_lifecycle_errors_do_not_propagate() -> None:
    manager = lifecycle()
    assert manager.create(runtime_v2_version="") is None
    assert manager.last_error == "environment_creation_failed"

    manager = lifecycle()
    manager.create(runtime_v2_version="2.0")
    manager.start()
    assert manager.create_session(correlation_id="contains private path C:\\secret") is None
    assert manager.last_error == "session_creation_failed"
