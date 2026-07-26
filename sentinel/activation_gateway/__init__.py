"""Public interfaces for the non-executing V2 activation gateway."""

from importlib import import_module

__all__ = [
    "ACTIVATION_GATEWAY_ENABLED",
    "V2_ACTIVATION_ALLOWED",
    "ActivationGateway",
    "ActivationGatewayAudit",
    "ActivationGatewayControl",
    "ActivationGatewayMetrics",
    "ActivationGatewayReport",
    "AuthoritySelectionDecisionV1",
    "GatewayEvidenceV1",
    "GatewayFallback",
    "RuntimeContextV1",
    "SelectedAuthority",
]

_EXPORTS = {
    "ACTIVATION_GATEWAY_ENABLED": (
        ".control",
        "ACTIVATION_GATEWAY_ENABLED",
    ),
    "V2_ACTIVATION_ALLOWED": (".control", "V2_ACTIVATION_ALLOWED"),
    "ActivationGateway": (".gateway", "ActivationGateway"),
    "ActivationGatewayAudit": (".audit", "ActivationGatewayAudit"),
    "ActivationGatewayControl": (".control", "ActivationGatewayControl"),
    "ActivationGatewayMetrics": (".metrics", "ActivationGatewayMetrics"),
    "ActivationGatewayReport": (".report", "ActivationGatewayReport"),
    "AuthoritySelectionDecisionV1": (
        ".decision",
        "AuthoritySelectionDecisionV1",
    ),
    "GatewayEvidenceV1": (".policy", "GatewayEvidenceV1"),
    "GatewayFallback": (".fallback", "GatewayFallback"),
    "RuntimeContextV1": (".policy", "RuntimeContextV1"),
    "SelectedAuthority": (".decision", "SelectedAuthority"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
