"""Public interfaces for isolated runtime equivalence validation."""

from importlib import import_module

__all__ = [
    "RUNTIME_EQUIVALENCE_VALIDATION_ENABLED",
    "EquivalenceClassification",
    "EquivalenceComparison",
    "EquivalenceMetrics",
    "EquivalenceMetricsSnapshot",
    "RuntimeEquivalenceControl",
    "RuntimeEquivalenceReport",
    "RuntimeEquivalenceResultV1",
    "RuntimeEquivalenceSnapshotV1",
    "RuntimeEquivalenceValidator",
]

_EXPORTS = {
    "RUNTIME_EQUIVALENCE_VALIDATION_ENABLED": (
        ".control",
        "RUNTIME_EQUIVALENCE_VALIDATION_ENABLED",
    ),
    "EquivalenceClassification": (
        ".equivalence",
        "EquivalenceClassification",
    ),
    "EquivalenceComparison": (".comparator", "EquivalenceComparison"),
    "EquivalenceMetrics": (".metrics", "EquivalenceMetrics"),
    "EquivalenceMetricsSnapshot": (
        ".metrics",
        "EquivalenceMetricsSnapshot",
    ),
    "RuntimeEquivalenceControl": (".control", "RuntimeEquivalenceControl"),
    "RuntimeEquivalenceReport": (".report", "RuntimeEquivalenceReport"),
    "RuntimeEquivalenceResultV1": (
        ".validator",
        "RuntimeEquivalenceResultV1",
    ),
    "RuntimeEquivalenceSnapshotV1": (
        ".equivalence",
        "RuntimeEquivalenceSnapshotV1",
    ),
    "RuntimeEquivalenceValidator": (
        ".validator",
        "RuntimeEquivalenceValidator",
    ),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
