"""Lazy public interfaces for controlled V2 shadow routing."""

from importlib import import_module


__all__ = [
    "ControlledRuntimeDiagnostics",
    "ControlledRuntimePipeline",
    "RuntimeComparisonStatus",
    "RuntimeShadowResultV1",
    "RuntimeV2ActivationState",
    "RuntimeV2Control",
    "RuntimeV2Router",
]


_EXPORTS = {
    "ControlledRuntimeDiagnostics": (
        ".diagnostics",
        "ControlledRuntimeDiagnostics",
    ),
    "ControlledRuntimePipeline": (".pipeline", "ControlledRuntimePipeline"),
    "RuntimeComparisonStatus": (
        ".comparison",
        "RuntimeComparisonStatus",
    ),
    "RuntimeShadowResultV1": (".diagnostics", "RuntimeShadowResultV1"),
    "RuntimeV2ActivationState": (
        ".control",
        "RuntimeV2ActivationState",
    ),
    "RuntimeV2Control": (".control", "RuntimeV2Control"),
    "RuntimeV2Router": (".router", "RuntimeV2Router"),
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
