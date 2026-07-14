import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from .confidence import ConfidenceEngine
from .config import AdvisoryConfig
from .models import AdvisoryAction, AdvisoryInsight, AdvisoryReport, InterventionLevel

logger = logging.getLogger(__name__)


class AdvisoryService:
    """Observes completed outcomes and returns advice; it has no execution capability."""

    def __init__(self, config: AdvisoryConfig | None = None, rules: Iterable[Any] = ()):
        self.config = config or AdvisoryConfig.from_env()
        self._confidence = ConfidenceEngine()
        self._rules = tuple(rules)

    def analyze(self, result: Any) -> AdvisoryReport | None:
        if not self.config.enabled:
            return None
        steps = list(getattr(result, "step_results", ()) or ())
        successful = sum(bool(getattr(step, "success", False)) for step in steps)
        failed = sum(
            not bool(getattr(step, "success", False)) and getattr(step, "status", "") != "skipped" for step in steps
        )
        retries = sum(max(0, int(getattr(step, "attempts", 0) or 0) - 1) for step in steps)
        fallbacks = sum(getattr(step, "recovery_strategy", "none") not in {"", "none", "retry"} for step in steps)
        tool_result = getattr(result, "tool_result", None)
        verified = int(bool(tool_result and getattr(tool_result, "success", False)))
        intent = getattr(getattr(result, "plan", None), "intent", None)
        intent_confidence = float(getattr(intent, "confidence", 0.0) or 0.0)
        conflicts = self._count_conflicts(tool_result)
        source_count, stale_sources = self._source_signals(tool_result)
        confidence = self._confidence.assess(
            intent_confidence=intent_confidence,
            successful_steps=successful,
            failed_steps=failed,
            retries=retries,
            fallbacks=fallbacks,
            has_error=bool(getattr(result, "error", None)),
            verified_outputs=verified,
            conflicts=conflicts,
            source_count=source_count,
            stale_sources=stale_sources,
        )
        insights: List[AdvisoryInsight] = []
        if getattr(result, "error", None) or failed:
            insights.append(
                AdvisoryInsight(
                    "risk",
                    "Resultado incompleto",
                    "Uno o más pasos fallaron; conviene revisar la causa antes de depender del resultado.",
                    InterventionLevel.WARNING,
                )
            )
        if conflicts:
            insights.append(
                AdvisoryInsight(
                    "contradiction",
                    "Evidencia contradictoria",
                    "Los resultados contienen indicadores incompatibles y requieren verificación adicional.",
                    InterventionLevel.WARNING,
                )
            )
        if stale_sources:
            insights.append(
                AdvisoryInsight(
                    "risk",
                    "Información potencialmente desactualizada",
                    f"{stale_sources} fuente(s) superan el umbral de vigencia configurado.",
                    InterventionLevel.SUGGESTION,
                )
            )
        if retries or fallbacks:
            insights.append(
                AdvisoryInsight(
                    "opportunity",
                    "Ruta poco estable",
                    "Una alternativa más simple o estable podría reducir reintentos y fallbacks.",
                    InterventionLevel.SUGGESTION,
                )
            )
        if confidence.score < 0.5 and not insights:
            insights.append(
                AdvisoryInsight(
                    "uncertainty",
                    "Confianza limitada",
                    "La evidencia disponible no basta para presentar esta salida como concluyente.",
                    InterventionLevel.SUGGESTION,
                )
            )
        for rule in self._rules:
            insights.extend(rule.evaluate(result, confidence))
        level = max((item.level for item in insights), default=InterventionLevel.NONE)
        actions = self._actions(intent, bool(insights))
        evidence = self._evidence(steps, tool_result)
        return AdvisoryReport(
            confidence.score,
            confidence.label,
            confidence.explanation,
            confidence.positives,
            confidence.negatives,
            insights,
            level,
            int(level) >= self.config.notification_threshold and bool(insights),
            actions,
            evidence,
        )

    @staticmethod
    def _count_conflicts(tool_result: Any) -> int:
        data = getattr(tool_result, "data", None)
        if not isinstance(data, dict):
            return 0
        conflicts = data.get("conflicts") or data.get("contradictions") or []
        return len(conflicts) if isinstance(conflicts, list) else int(bool(conflicts))

    def _source_signals(self, tool_result: Any) -> tuple[int, int]:
        data = getattr(tool_result, "data", None)
        if not isinstance(data, dict) or not isinstance(data.get("sources"), list):
            return 0, 0
        sources = data["sources"]
        stale = 0
        now = datetime.now(timezone.utc)
        for source in sources:
            if not isinstance(source, dict):
                continue
            raw = source.get("timestamp") or source.get("updated_at") or source.get("published_at")
            if not raw:
                continue
            try:
                parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                stale += (now - parsed).total_seconds() > self.config.stale_after_hours * 3600
            except (TypeError, ValueError):
                stale += 1
        return len(sources), stale

    @staticmethod
    def _evidence(steps: List[Any], tool_result: Any) -> List[Dict[str, Any]]:
        evidence = [
            {
                "type": "tool",
                "id": getattr(s, "executed_tool_id", None) or getattr(s, "tool_id", ""),
                "verified": bool(getattr(s, "success", False)),
            }
            for s in steps
        ]
        if not steps and tool_result:
            evidence.append(
                {
                    "type": "tool_result",
                    "id": getattr(tool_result, "tool_id", "unknown"),
                    "verified": bool(getattr(tool_result, "success", False)),
                }
            )
        return evidence

    @staticmethod
    def _actions(intent: Any, has_insights: bool) -> List[AdvisoryAction]:
        if not has_insights:
            return []
        request = getattr(intent, "raw_input", "esta tarea") or "esta tarea"
        return [
            AdvisoryAction("continue", "Continuar", local_action="dismiss"),
            AdvisoryAction(
                "investigate", "Investigar alternativas", f"Investiga alternativas más confiables para: {request}"
            ),
            AdvisoryAction("simplify", "Simplificar", f"Propón una estrategia más simple y reversible para: {request}"),
            AdvisoryAction(
                "explain", "Explicar por qué", f"Explica la incertidumbre, riesgos y evidencia de: {request}"
            ),
            AdvisoryAction("evidence", "Ver evidencia/fuentes", local_action="show_evidence"),
        ]
