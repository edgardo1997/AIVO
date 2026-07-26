"""Human-readable aggregate trust evaluation report."""

from dataclasses import dataclass

from .evaluator import TrustEvaluationResultV1


@dataclass(frozen=True)
class TrustEvaluationReport:
    result: TrustEvaluationResultV1
    risks: tuple[str, ...]

    def human_readable(self) -> str:
        return (
            "SENTINEL V2 TRUST EVALUATION REPORT\n\n"
            f"Confianza actual: {self.result.confidence.value}\n"
            f"Score: {self.result.score:.2f}\n"
            f"Factores positivos: "
            f"{', '.join(self.result.positive_factors) or 'Ninguno'}\n"
            f"Factores negativos: "
            f"{', '.join(self.result.negative_factors) or 'Ninguno'}\n"
            f"Recomendación: {self.result.recommendation.value}\n"
            f"Riesgos restantes: "
            f"{', '.join(self.risks) if self.risks else 'Ninguno'}"
        )
