"""Public interfaces for the isolated controlled canary environment."""

from importlib import import_module

__all__ = [
    "CANARY_ENVIRONMENT_ENABLED",
    "CanaryEnvironmentControl",
    "CanaryEnvironmentLifecycle",
    "CanaryEnvironmentMetrics",
    "CanaryEnvironmentReport",
    "CanaryEnvironmentState",
    "CanaryEnvironmentV1",
    "CanaryHealthEvaluator",
    "CanaryHealthStatus",
    "CanaryMetricsSnapshot",
    "CanarySessionV1",
]

_EXPORTS = {
    "CANARY_ENVIRONMENT_ENABLED": (".control", "CANARY_ENVIRONMENT_ENABLED"),
    "CanaryEnvironmentControl": (".control", "CanaryEnvironmentControl"),
    "CanaryEnvironmentLifecycle": (
        ".lifecycle",
        "CanaryEnvironmentLifecycle",
    ),
    "CanaryEnvironmentMetrics": (".metrics", "CanaryEnvironmentMetrics"),
    "CanaryEnvironmentReport": (".report", "CanaryEnvironmentReport"),
    "CanaryEnvironmentState": (".environment", "CanaryEnvironmentState"),
    "CanaryEnvironmentV1": (".environment", "CanaryEnvironmentV1"),
    "CanaryHealthEvaluator": (".health", "CanaryHealthEvaluator"),
    "CanaryHealthStatus": (".health", "CanaryHealthStatus"),
    "CanaryMetricsSnapshot": (".metrics", "CanaryMetricsSnapshot"),
    "CanarySessionV1": (".session", "CanarySessionV1"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
