"""Human-readable sandbox execution report."""

from .executor import ExecutorSandboxEnvelopeV1


def render_executor_sandbox_report(envelope: ExecutorSandboxEnvelopeV1) -> str:
    return "\n".join(
        (
            "SENTINEL EXECUTOR SANDBOX V2 REPORT",
            f"State: {envelope.result.final_state.value}",
            f"Simulated steps: {len(envelope.result.simulated_steps)}",
            "Authority: false",
            "Execution requested: false",
        )
    )
