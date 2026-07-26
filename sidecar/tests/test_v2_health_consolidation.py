from sentinel.canary_environment.health import CanaryHealthStatus
from sentinel.canary_observation.health import (
    CanaryHealthReport,
    CanaryHealthStatus as ObservationHealthStatus,
)
from sentinel.contracts import HealthStateV1, HealthStatusV1
from sentinel.controlled_runtime_activation.health import ActivationHealthStatus
from sentinel.decision_long_term_evaluation.health import (
    DecisionLongTermHealthStatus,
)
from sentinel.runtime_trial.health import RuntimeTrialHealthStatus
from sentinel.v2_operational_observability.health import OperationalHealthStatus


def test_all_v2_health_vocabularies_are_central():
    aliases = (
        CanaryHealthStatus,
        ObservationHealthStatus,
        ActivationHealthStatus,
        DecisionLongTermHealthStatus,
        RuntimeTrialHealthStatus,
        OperationalHealthStatus,
    )
    assert all(alias is HealthStateV1 for alias in aliases)
    assert set(HealthStateV1.__members__) == {
        "HEALTHY",
        "OBSERVING",
        "WARNING",
        "DEGRADED",
        "CRITICAL",
    }


def test_canary_health_report_is_a_central_health_contract():
    report = CanaryHealthReport(
        state=HealthStateV1.OBSERVING,
        reasons=("disabled",),
    )
    assert isinstance(report, HealthStatusV1)
    assert report.authority is False
    assert report.execution_requested is False
