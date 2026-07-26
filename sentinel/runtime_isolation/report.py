"""Human-readable passive isolation report."""

from .isolation import RuntimeIsolationEnvelopeV1


def render_runtime_isolation_report(
    envelope: RuntimeIsolationEnvelopeV1,
) -> str:
    return "\n".join(
        (
            "SENTINEL RUNTIME ISOLATION V2 REPORT",
            f"Status: {envelope.context.status.value}",
            f"Level: {envelope.context.isolation_level.value}",
            "Authority: false",
            "Execution requested: false",
        )
    )
