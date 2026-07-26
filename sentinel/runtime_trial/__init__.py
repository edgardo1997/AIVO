"""Public interfaces for the isolated controlled V2 runtime trial."""

from importlib import import_module

__all__ = [
    "RUNTIME_TRIAL_ENABLED",
    "RuntimeTrialComparison",
    "RuntimeTrialComparisonStatus",
    "RuntimeTrialControl",
    "RuntimeTrialHealthEvaluator",
    "RuntimeTrialHealthStatus",
    "RuntimeTrialMetrics",
    "RuntimeTrialMetricsSnapshot",
    "RuntimeTrialReport",
    "RuntimeTrialResult",
    "RuntimeTrialRunner",
    "RuntimeTrialStatus",
    "RuntimeTrialV1",
    "SanitizedScenarioV1",
    "ScenarioKind",
    "SimulatedExecutor",
    "SimulatedResult",
]

_EXPORTS = {
    "RUNTIME_TRIAL_ENABLED": (".control", "RUNTIME_TRIAL_ENABLED"),
    "RuntimeTrialComparison": (".comparison", "RuntimeTrialComparison"),
    "RuntimeTrialComparisonStatus": (
        ".comparison",
        "RuntimeTrialComparisonStatus",
    ),
    "RuntimeTrialControl": (".control", "RuntimeTrialControl"),
    "RuntimeTrialHealthEvaluator": (".health", "RuntimeTrialHealthEvaluator"),
    "RuntimeTrialHealthStatus": (".health", "RuntimeTrialHealthStatus"),
    "RuntimeTrialMetrics": (".metrics", "RuntimeTrialMetrics"),
    "RuntimeTrialMetricsSnapshot": (".metrics", "RuntimeTrialMetricsSnapshot"),
    "RuntimeTrialReport": (".report", "RuntimeTrialReport"),
    "RuntimeTrialResult": (".trial", "RuntimeTrialResult"),
    "RuntimeTrialRunner": (".trial", "RuntimeTrialRunner"),
    "RuntimeTrialStatus": (".trial", "RuntimeTrialStatus"),
    "RuntimeTrialV1": (".trial", "RuntimeTrialV1"),
    "SanitizedScenarioV1": (".scenario", "SanitizedScenarioV1"),
    "ScenarioKind": (".scenario", "ScenarioKind"),
    "SimulatedExecutor": (".executor", "SimulatedExecutor"),
    "SimulatedResult": (".executor", "SimulatedResult"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
