"""Lazy public interfaces for isolated runtime replay validation."""

from importlib import import_module


__all__ = [
    "RUNTIME_REPLAY_VALIDATION_ENABLED",
    "ReplayComparisonStatus",
    "ReplayDatasetV1",
    "ReplayExecutionResultV1",
    "ReplayMetrics",
    "ReplayMetricsSnapshot",
    "ReplayValidationControl",
    "ReplayValidationReport",
    "ReplayValidationState",
    "RuntimeReplayRunner",
]


_EXPORTS = {
    "RUNTIME_REPLAY_VALIDATION_ENABLED": (
        ".control",
        "RUNTIME_REPLAY_VALIDATION_ENABLED",
    ),
    "ReplayComparisonStatus": (
        ".comparison",
        "ReplayComparisonStatus",
    ),
    "ReplayDatasetV1": (".dataset", "ReplayDatasetV1"),
    "ReplayExecutionResultV1": (
        ".replay",
        "ReplayExecutionResultV1",
    ),
    "ReplayMetrics": (".metrics", "ReplayMetrics"),
    "ReplayMetricsSnapshot": (".metrics", "ReplayMetricsSnapshot"),
    "ReplayValidationControl": (".control", "ReplayValidationControl"),
    "ReplayValidationReport": (".report", "ReplayValidationReport"),
    "ReplayValidationState": (".control", "ReplayValidationState"),
    "RuntimeReplayRunner": (".replay", "RuntimeReplayRunner"),
}


def __getattr__(name: str):
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    module = import_module(module_name, __name__)
    value = getattr(module, attribute)
    globals()[name] = value
    return value
