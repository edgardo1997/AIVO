"""Public interfaces for reversible, non-executing canary activation."""

from importlib import import_module

__all__ = [
    "CONTROLLED_RUNTIME_ACTIVATION_ENABLED",
    "MAX_V2_TRAFFIC_PERCENTAGE",
    "V2_CANARY_ENABLED",
    "V2_TRAFFIC_PERCENTAGE",
    "ActivationAudit",
    "ActivationHealthEvaluator",
    "ActivationHealthStatus",
    "ActivationMetrics",
    "ActivationReport",
    "ActivationState",
    "CanaryRoutingEvidenceV1",
    "CanaryExecutionResultV1",
    "CanaryKillSwitch",
    "ControlledCanaryExecutor",
    "ControlledActivationControl",
    "ControlledRuntimeActivation",
    "ControlledRuntimeRouter",
    "RollbackManager",
    "RollbackState",
    "RuntimeRouteDecisionV1",
    "RuntimeSelection",
]

_EXPORTS = {
    "CONTROLLED_RUNTIME_ACTIVATION_ENABLED": (
        ".control",
        "CONTROLLED_RUNTIME_ACTIVATION_ENABLED",
    ),
    "MAX_V2_TRAFFIC_PERCENTAGE": (
        ".control",
        "MAX_V2_TRAFFIC_PERCENTAGE",
    ),
    "V2_CANARY_ENABLED": (".control", "V2_CANARY_ENABLED"),
    "V2_TRAFFIC_PERCENTAGE": (".control", "V2_TRAFFIC_PERCENTAGE"),
    "ActivationAudit": (".audit", "ActivationAudit"),
    "ActivationHealthEvaluator": (".health", "ActivationHealthEvaluator"),
    "ActivationHealthStatus": (".health", "ActivationHealthStatus"),
    "ActivationMetrics": (".metrics", "ActivationMetrics"),
    "ActivationReport": (".report", "ActivationReport"),
    "ActivationState": (".activation", "ActivationState"),
    "CanaryRoutingEvidenceV1": (
        ".canary_policy",
        "CanaryRoutingEvidenceV1",
    ),
    "CanaryExecutionResultV1": (
        ".canary_execution",
        "CanaryExecutionResultV1",
    ),
    "CanaryKillSwitch": (".kill_switch", "CanaryKillSwitch"),
    "ControlledCanaryExecutor": (
        ".canary_execution",
        "ControlledCanaryExecutor",
    ),
    "ControlledActivationControl": (
        ".control",
        "ControlledActivationControl",
    ),
    "ControlledRuntimeActivation": (
        ".activation",
        "ControlledRuntimeActivation",
    ),
    "ControlledRuntimeRouter": (".router", "ControlledRuntimeRouter"),
    "RollbackManager": (".rollback", "RollbackManager"),
    "RollbackState": (".rollback", "RollbackState"),
    "RuntimeRouteDecisionV1": (".router", "RuntimeRouteDecisionV1"),
    "RuntimeSelection": (".router", "RuntimeSelection"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
