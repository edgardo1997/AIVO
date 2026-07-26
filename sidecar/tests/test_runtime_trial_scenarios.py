from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from sentinel.canary_environment import (
    CanaryEnvironmentState,
    CanaryEnvironmentV1,
)
from sentinel.runtime_trial import (
    RuntimeTrialControl,
    RuntimeTrialRunner,
    SanitizedScenarioV1,
    ScenarioKind,
)


def environment() -> CanaryEnvironmentV1:
    return CanaryEnvironmentV1.create(
        runtime_v2_version="2.0",
        created_at=datetime.now(timezone.utc),
    ).model_copy(update={"state": CanaryEnvironmentState.RUNNING})


def test_all_sanitized_scenarios_run() -> None:
    runner = RuntimeTrialRunner(control=RuntimeTrialControl(enabled=True))
    results = [
        runner.run_scenario(
            environment=environment(),
            scenario=SanitizedScenarioV1.create(kind),
        )
        for kind in ScenarioKind
    ]
    assert all(result is not None for result in results)
    assert runner.metrics.snapshot().scenarios_run == 3
    assert runner.metrics.snapshot().successes == 3


def test_scenario_has_no_freeform_payload() -> None:
    scenario = SanitizedScenarioV1.create(ScenarioKind.KNOWN_APPLICATION)
    assert set(scenario.model_fields) == {
        "schema_version",
        "scenario_id",
        "kind",
        "scenario_hash",
    }
    with pytest.raises(ValidationError):
        SanitizedScenarioV1(
            **scenario.model_dump(),
            command="start process",
        )


def test_comparison_detects_expected_and_critical_differences() -> None:
    runner = RuntimeTrialRunner(control=RuntimeTrialControl(enabled=True))
    scenario = SanitizedScenarioV1.create(ScenarioKind.SIMPLE_WORKFLOW)
    first = runner.run_scenario(
        environment=environment(),
        scenario=scenario,
    )
    assert first is not None
    expected = {
        "intent_hash": first.intent_hash,
        "plan_hash": first.plan_hash,
        "discovery_hash": first.discovery_hash,
        "policy_hash": first.policy_hash,
        "authorization_hash": first.authorization_hash,
    }
    matched = runner.run_scenario(
        environment=environment(),
        scenario=scenario,
        expected=expected,
    )
    assert matched is not None
    assert matched.comparison.value == "MATCH"
    expected["policy_hash"] = "0" * 64
    critical = runner.run_scenario(
        environment=environment(),
        scenario=scenario,
        expected=expected,
    )
    assert critical is not None
    assert critical.comparison.value == "CRITICAL_DIVERGENCE"
