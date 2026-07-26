"""Public interfaces for aggregate long-term decision evaluation."""

from importlib import import_module

__all__ = [
    "DECISION_LONG_TERM_ENABLED",
    "DecisionAggregateSnapshot",
    "DecisionLongTermControl",
    "DecisionLongTermHealthEvaluator",
    "DecisionLongTermHealthStatus",
    "DecisionLongTermMetrics",
    "DecisionLongTermReport",
    "DecisionTrendAnalyzer",
    "EvaluationWindowState",
    "EvaluationWindowV1",
    "LongTermEvaluationEngine",
    "TrendStatus",
]

_EXPORTS = {
    "DECISION_LONG_TERM_ENABLED": (".control", "DECISION_LONG_TERM_ENABLED"),
    "DecisionAggregateSnapshot": (
        ".aggregation",
        "DecisionAggregateSnapshot",
    ),
    "DecisionLongTermControl": (".control", "DecisionLongTermControl"),
    "DecisionLongTermHealthEvaluator": (
        ".health",
        "DecisionLongTermHealthEvaluator",
    ),
    "DecisionLongTermHealthStatus": (
        ".health",
        "DecisionLongTermHealthStatus",
    ),
    "DecisionLongTermMetrics": (".metrics", "DecisionLongTermMetrics"),
    "DecisionLongTermReport": (".report", "DecisionLongTermReport"),
    "DecisionTrendAnalyzer": (".trend", "DecisionTrendAnalyzer"),
    "EvaluationWindowState": (".window", "EvaluationWindowState"),
    "EvaluationWindowV1": (".window", "EvaluationWindowV1"),
    "LongTermEvaluationEngine": (".collector", "LongTermEvaluationEngine"),
    "TrendStatus": (".trend", "TrendStatus"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
