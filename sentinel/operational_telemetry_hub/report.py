"""Human-readable telemetry summary without operational payloads."""

from dataclasses import dataclass

from sentinel.contracts import HealthStatusV1

from .metrics import OperationalMetricSnapshotV1


@dataclass(frozen=True)
class OperationalTelemetryReport:
    metrics: OperationalMetricSnapshotV1
    health: HealthStatusV1
    risks: tuple[str, ...]
    authority: bool = False
    execution_requested: bool = False

    def render(self) -> str:
        return "\n".join(
            (
                "SENTINEL V2 OPERATIONAL TELEMETRY HUB REPORT",
                f"Health: {self.health.state.value}",
                f"Decisions: {self.metrics.decisions}",
                f"Divergences: {self.metrics.divergences}",
                f"Errors: {self.metrics.errors}",
                f"Rollbacks: {self.metrics.rollbacks}",
                f"Risks: {', '.join(self.risks) if self.risks else 'None'}",
                "Authority: false",
                "Execution requested: false",
            )
        )
