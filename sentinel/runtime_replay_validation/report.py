"""Human-readable aggregate runtime replay validation report."""

from dataclasses import dataclass

from .comparison import ReplayComparisonStatus
from .dataset import ReplayDatasetV1
from .metrics import ReplayMetricsSnapshot
from .replay import ReplayExecutionResultV1


@dataclass(frozen=True)
class ReplayValidationReport:
    dataset: str
    events_processed: int
    match_rate: float
    divergences: int
    stability: str
    determinism: dict[str, dict[str, int]]
    risks: tuple[str, ...]

    @classmethod
    def build(
        cls,
        dataset: ReplayDatasetV1,
        results: tuple[ReplayExecutionResultV1, ...],
        metrics: ReplayMetricsSnapshot,
    ) -> "ReplayValidationReport":
        counts = {
            status.value: sum(result.comparison_result is status for result in results)
            for status in ReplayComparisonStatus
        }
        processed = metrics.processed_events
        match_rate = 100.0 * metrics.matches / processed if processed else 0.0
        risks = []
        if metrics.divergences:
            risks.append("replay_divergences_detected")
        if metrics.errors:
            risks.append("shadow_errors_detected")
        if metrics.non_deterministic_results:
            risks.append("non_determinism_detected")
        if not results:
            risks.append("insufficient_replay_evidence")
        return cls(
            dataset=f"{dataset.event_id}:{dataset.version}",
            events_processed=processed,
            match_rate=match_rate,
            divergences=metrics.divergences,
            stability=("STABLE" if not metrics.non_deterministic_results and not metrics.errors else "UNSTABLE"),
            determinism={dataset.event_id: counts},
            risks=tuple(risks),
        )

    def human_readable(self) -> str:
        counts = self.determinism.get(self.dataset.split(":")[0], {})
        lines = "\n".join(f"- {name}: {value}" for name, value in counts.items())
        risks = "\n".join(f"- {risk}" for risk in self.risks) if self.risks else "- Ninguno"
        return (
            "SENTINEL RUNTIME REPLAY VALIDATION REPORT\n\n"
            f"Dataset utilizado:\n{self.dataset}\n\n"
            f"Eventos procesados:\n{self.events_processed}\n\n"
            f"Tasa de coincidencia:\n{self.match_rate:.2f}%\n\n"
            f"Divergencias encontradas:\n{self.divergences}\n\n"
            f"Estabilidad:\n{self.stability}\n\n"
            f"Determinismo:\n{lines}\n\n"
            f"Riesgos:\n{risks}"
        )
