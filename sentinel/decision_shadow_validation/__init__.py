"""Public interfaces for non-authoritative decision shadow validation."""

from importlib import import_module

__all__ = [
    "DECISION_SHADOW_VALIDATION_ENABLED",
    "ComponentComparison",
    "ComponentComparisonStatus",
    "DecisionClassification",
    "DecisionComparison",
    "DecisionShadowMetrics",
    "DecisionShadowMetricsSnapshot",
    "DecisionShadowReport",
    "DecisionShadowResultV1",
    "DecisionShadowValidationControl",
    "DecisionShadowValidationEngine",
    "LegacyDecisionSnapshot",
    "V2DecisionSnapshot",
]

_EXPORTS = {
    "DECISION_SHADOW_VALIDATION_ENABLED": (
        ".control",
        "DECISION_SHADOW_VALIDATION_ENABLED",
    ),
    "ComponentComparison": (".comparison", "ComponentComparison"),
    "ComponentComparisonStatus": (
        ".comparison",
        "ComponentComparisonStatus",
    ),
    "DecisionClassification": (".classification", "DecisionClassification"),
    "DecisionComparison": (".comparison", "DecisionComparison"),
    "DecisionShadowMetrics": (".metrics", "DecisionShadowMetrics"),
    "DecisionShadowMetricsSnapshot": (
        ".metrics",
        "DecisionShadowMetricsSnapshot",
    ),
    "DecisionShadowReport": (".report", "DecisionShadowReport"),
    "DecisionShadowResultV1": (".validator", "DecisionShadowResultV1"),
    "DecisionShadowValidationControl": (
        ".control",
        "DecisionShadowValidationControl",
    ),
    "DecisionShadowValidationEngine": (
        ".validator",
        "DecisionShadowValidationEngine",
    ),
    "LegacyDecisionSnapshot": (
        ".decision_capture",
        "LegacyDecisionSnapshot",
    ),
    "V2DecisionSnapshot": (".decision_capture", "V2DecisionSnapshot"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
