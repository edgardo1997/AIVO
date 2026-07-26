"""Public interfaces for isolated V2 operational observability."""

from importlib import import_module

__all__ = [
    "V2_OPERATIONAL_OBSERVABILITY_ENABLED",
    "AlertRecommendation",
    "IncidentClassification",
    "ObservationBatchV1",
    "ObservationResultV1",
    "OperationalHealthStatus",
    "OperationalMetrics",
    "OperationalObserver",
    "OperationalReport",
    "OperationalTimeline",
    "V2OperationalObservabilityControl",
]

_EXPORTS = {
    "V2_OPERATIONAL_OBSERVABILITY_ENABLED": (
        ".control",
        "V2_OPERATIONAL_OBSERVABILITY_ENABLED",
    ),
    "AlertRecommendation": (".alerts", "AlertRecommendation"),
    "IncidentClassification": (".incident", "IncidentClassification"),
    "ObservationBatchV1": (".observer", "ObservationBatchV1"),
    "ObservationResultV1": (".observer", "ObservationResultV1"),
    "OperationalHealthStatus": (".health", "OperationalHealthStatus"),
    "OperationalMetrics": (".metrics", "OperationalMetrics"),
    "OperationalObserver": (".observer", "OperationalObserver"),
    "OperationalReport": (".report", "OperationalReport"),
    "OperationalTimeline": (".timeline", "OperationalTimeline"),
    "V2OperationalObservabilityControl": (
        ".control",
        "V2OperationalObservabilityControl",
    ),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
