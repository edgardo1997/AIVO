from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class ConfidenceAssessment:
    score: float
    label: str
    explanation: str
    positives: List[str]
    negatives: List[str]


class ConfidenceEngine:
    """Transparent heuristic estimate; intentionally not a probability model."""

    def assess(self, *, intent_confidence: float, successful_steps: int, failed_steps: int,
               retries: int, fallbacks: int, has_error: bool, verified_outputs: int,
               conflicts: int, source_count: int = 0, stale_sources: int = 0) -> ConfidenceAssessment:
        score = 0.45
        positives: List[str] = []
        negatives: List[str] = []
        if intent_confidence >= 0.75:
            score += 0.15
            positives.append("La intención fue interpretada con alta confianza")
        elif intent_confidence < 0.5:
            score -= 0.15
            negatives.append("La interpretación de la intención tiene baja confianza")
        if successful_steps:
            score += min(0.25, successful_steps * 0.08)
            positives.append(f"{successful_steps} paso(s) finalizaron correctamente")
        if verified_outputs:
            score += min(0.15, verified_outputs * 0.07)
            positives.append(f"{verified_outputs} resultado(s) fueron verificados por herramientas")
        if source_count:
            score += min(0.12, source_count * 0.03)
            positives.append(f"Se declararon {source_count} fuente(s)")
        if stale_sources:
            score -= min(0.2, stale_sources * 0.08)
            negatives.append(f"{stale_sources} fuente(s) pueden estar desactualizadas")
        if failed_steps or has_error:
            score -= min(0.4, 0.18 + failed_steps * 0.1)
            negatives.append(f"Se detectaron {max(1, failed_steps)} fallo(s) de ejecución")
        if retries:
            score -= min(0.12, retries * 0.03)
            negatives.append(f"La ejecución necesitó {retries} reintento(s)")
        if fallbacks:
            score -= min(0.12, fallbacks * 0.05)
            negatives.append(f"Se usaron {fallbacks} ruta(s) alternativa(s)")
        if conflicts:
            score -= min(0.3, conflicts * 0.15)
            negatives.append(f"Hay {conflicts} contradicción(es) en la evidencia")
        score = round(max(0.0, min(1.0, score)), 2)
        label = "alta" if score >= 0.75 else "media" if score >= 0.5 else "baja"
        explanation = (
            f"Estimación razonada {label} ({score:.0%}); no representa una probabilidad matemática. "
            "Se deriva de la interpretación, ejecución, verificaciones, reintentos y conflictos observados."
        )
        return ConfidenceAssessment(score, label, explanation, positives, negatives)
