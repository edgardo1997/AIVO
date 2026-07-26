"""Public interfaces for non-authoritative V2 migration readiness."""

from importlib import import_module

__all__ = [
    "V2_AUTHORITY_READINESS_ENABLED",
    "AuthorityReadinessMetrics",
    "AuthorityReadinessMetricsSnapshot",
    "AuthorityReadinessReport",
    "AuthorityReadinessResultV1",
    "AuthorityReadinessState",
    "GateResult",
    "ReadinessEvidenceV1",
    "V2AuthorityReadinessControl",
    "V2AuthorityReadinessEngine",
]

_EXPORTS = {
    "V2_AUTHORITY_READINESS_ENABLED": (
        ".control",
        "V2_AUTHORITY_READINESS_ENABLED",
    ),
    "AuthorityReadinessMetrics": (".metrics", "AuthorityReadinessMetrics"),
    "AuthorityReadinessMetricsSnapshot": (
        ".metrics",
        "AuthorityReadinessMetricsSnapshot",
    ),
    "AuthorityReadinessReport": (".report", "AuthorityReadinessReport"),
    "AuthorityReadinessResultV1": (
        ".validator",
        "AuthorityReadinessResultV1",
    ),
    "AuthorityReadinessState": (".readiness", "AuthorityReadinessState"),
    "GateResult": (".gates", "GateResult"),
    "ReadinessEvidenceV1": (".gates", "ReadinessEvidenceV1"),
    "V2AuthorityReadinessControl": (
        ".control",
        "V2AuthorityReadinessControl",
    ),
    "V2AuthorityReadinessEngine": (
        ".validator",
        "V2AuthorityReadinessEngine",
    ),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
