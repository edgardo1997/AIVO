from datetime import datetime, timezone

from sentinel.canary_environment import (
    CanaryEnvironmentState,
    CanaryEnvironmentV1,
)
from sentinel.runtime_trial import (
    RUNTIME_TRIAL_ENABLED,
    RuntimeTrialControl,
    RuntimeTrialRunner,
    RuntimeTrialStatus,
    SanitizedScenarioV1,
    ScenarioKind,
    SimulatedResult,
)


def environment() -> CanaryEnvironmentV1:
    return CanaryEnvironmentV1.create(
        runtime_v2_version="2.0",
        created_at=datetime.now(timezone.utc),
    ).model_copy(update={"state": CanaryEnvironmentState.RUNNING})


def test_trial_disabled_by_default() -> None:
    assert RUNTIME_TRIAL_ENABLED is False
    runner = RuntimeTrialRunner(control=RuntimeTrialControl(environ={}))
    result = runner.run_scenario(
        environment=environment(),
        scenario=SanitizedScenarioV1.create(ScenarioKind.KNOWN_APPLICATION),
    )
    assert result is None
    assert runner.metrics.snapshot().scenarios_run == 0


def test_trial_requires_running_canary_environment() -> None:
    stopped = environment().model_copy(update={"state": CanaryEnvironmentState.STOPPED})
    runner = RuntimeTrialRunner(control=RuntimeTrialControl(enabled=True))
    assert (
        runner.run_scenario(
            environment=stopped,
            scenario=SanitizedScenarioV1.create(ScenarioKind.KNOWN_APPLICATION),
        )
        is None
    )
    assert runner.metrics.snapshot().scenarios_run == 0


def test_complete_simulated_trial() -> None:
    runner = RuntimeTrialRunner(control=RuntimeTrialControl(enabled=True))
    result = runner.run_scenario(
        environment=environment(),
        scenario=SanitizedScenarioV1.create(ScenarioKind.KNOWN_APPLICATION),
    )
    assert result is not None
    assert result.trial.status is RuntimeTrialStatus.COMPLETED
    assert result.simulated_result is SimulatedResult.SIMULATED_SUCCESS
    assert result.authority is False
    assert result.trial.authority is False
    assert result.trial.timestamp.utcoffset() is not None
    assert len(result.stage_states) == 5
    assert result.conversions == 5


def test_simulated_failure_and_exception_are_isolated() -> None:
    class FailingSimulator:
        def simulate(self, *, should_succeed):
            raise RuntimeError("private failure")

    runner = RuntimeTrialRunner(
        control=RuntimeTrialControl(enabled=True),
        simulated_executor=FailingSimulator(),
    )
    result = runner.run_scenario(
        environment=environment(),
        scenario=SanitizedScenarioV1.create(ScenarioKind.SIMPLE_WORKFLOW),
    )
    assert result is not None
    assert result.trial.status is RuntimeTrialStatus.FAILED
    assert "private failure" not in result.model_dump_json()


def test_results_are_immutable() -> None:
    runner = RuntimeTrialRunner(control=RuntimeTrialControl(enabled=True))
    result = runner.run_scenario(
        environment=environment(),
        scenario=SanitizedScenarioV1.create(ScenarioKind.SETTINGS_CHANGE),
    )
    assert result is not None
    try:
        result.authority = True
    except Exception:
        pass
    assert result.authority is False
