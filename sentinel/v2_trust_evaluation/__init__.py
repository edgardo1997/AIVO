"""Public interfaces for isolated V2 trust evaluation."""

from importlib import import_module

__all__ = [
    "V2_TRUST_EVALUATION_ENABLED",
    "ConfidenceState",
    "HistoricalEvidenceV1",
    "HistorySummary",
    "RecommendationState",
    "TrustCriteriaV1",
    "TrustEvaluationControl",
    "TrustEvaluationMetrics",
    "TrustEvaluationReport",
    "TrustEvaluationResultV1",
    "TrustEvaluator",
]

_EXPORTS = {
    "V2_TRUST_EVALUATION_ENABLED": (
        ".control",
        "V2_TRUST_EVALUATION_ENABLED",
    ),
    "ConfidenceState": (".confidence", "ConfidenceState"),
    "HistoricalEvidenceV1": (".history", "HistoricalEvidenceV1"),
    "HistorySummary": (".history", "HistorySummary"),
    "RecommendationState": (".recommendation", "RecommendationState"),
    "TrustCriteriaV1": (".criteria", "TrustCriteriaV1"),
    "TrustEvaluationControl": (".control", "TrustEvaluationControl"),
    "TrustEvaluationMetrics": (".metrics", "TrustEvaluationMetrics"),
    "TrustEvaluationReport": (".report", "TrustEvaluationReport"),
    "TrustEvaluationResultV1": (".evaluator", "TrustEvaluationResultV1"),
    "TrustEvaluator": (".evaluator", "TrustEvaluator"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
