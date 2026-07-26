"""Public interfaces for final non-authoritative control-plane readiness."""

from importlib import import_module

__all__ = [
    "FINAL_CONTROL_PLANE_READINESS_ENABLED",
    "ConsolidatedSignalsV1",
    "FinalControlPlaneAggregator",
    "FinalControlPlaneControl",
    "FinalReadinessDecision",
    "FinalReadinessMetrics",
    "FinalReadinessReport",
    "FinalReadinessStatus",
    "GateResult",
]

_EXPORTS = {
    "FINAL_CONTROL_PLANE_READINESS_ENABLED": (
        ".control",
        "FINAL_CONTROL_PLANE_READINESS_ENABLED",
    ),
    "ConsolidatedSignalsV1": (".signals", "ConsolidatedSignalsV1"),
    "FinalControlPlaneAggregator": (
        ".aggregator",
        "FinalControlPlaneAggregator",
    ),
    "FinalControlPlaneControl": (".control", "FinalControlPlaneControl"),
    "FinalReadinessDecision": (".decision", "FinalReadinessDecision"),
    "FinalReadinessMetrics": (".metrics", "FinalReadinessMetrics"),
    "FinalReadinessReport": (".report", "FinalReadinessReport"),
    "FinalReadinessStatus": (".decision", "FinalReadinessStatus"),
    "GateResult": (".gates", "GateResult"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
