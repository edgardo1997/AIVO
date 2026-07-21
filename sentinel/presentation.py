"""User-facing translation of governed Sentinel execution results.

This module never decides or executes. It only translates trusted pipeline
state into a stable, progressive-disclosure contract.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional


class PresentationMode(str, Enum):
    USER = "user"
    DEVELOPER = "developer"

    @classmethod
    def parse(cls, value: Any) -> "PresentationMode":
        return cls.DEVELOPER if str(value).lower() == cls.DEVELOPER.value else cls.USER


class PresentationLayer:
    """Translate an ExecutionResult without changing its authority or data."""

    def present(self, result: Any, mode: PresentationMode = PresentationMode.USER) -> Dict[str, Any]:
        status = self._status(result)
        risk_score = getattr(getattr(result, "decision", None), "final_risk_score", None)
        evidence = list(getattr(result, "grounding_results", []) or [])
        grounded_count = sum(1 for item in evidence if item.get("grounded"))
        required_count = sum(1 for item in evidence if item.get("required"))
        presentation = {
            "version": 1,
            "mode": mode.value,
            "status": status,
            "title": self._title(status),
            "summary": self.summary(result),
            "risk": {
                "level": self._risk_level(risk_score),
                "score": risk_score if mode is PresentationMode.DEVELOPER else None,
            },
            "evidence": {
                "required": required_count,
                "verified": grounded_count,
                "satisfied": bool(getattr(result, "grounding_satisfied", True)),
                "sources": [
                    {
                        "category": item.get("category"),
                        "tool": item.get("tool_id") if mode is PresentationMode.DEVELOPER else None,
                        "verified": bool(item.get("grounded")),
                    }
                    for item in evidence
                ],
            },
            "next_action": self._next_action(result, status),
            "details": self._details(result) if mode is PresentationMode.DEVELOPER else None,
        }
        return presentation

    def summary(self, result: Any) -> str:
        if not result:
            return "Sentinel no recibió un resultado que pueda presentar."
        intent = result.plan.intent
        if intent.confidence < 0.6:
            return "No identifiqué una acción segura para ejecutar. Puedes explicar con más detalle qué necesitas."
        if result.blocked and result.action_id:
            reason = result.simulation_summary or "La acción necesita tu autorización."
            return f"Todavía no ejecuté la acción. {reason}"
        if result.error or (result.tool_result and not result.tool_result.success):
            raw_error = str(result.error or getattr(result.tool_result, "error", ""))
            if "required" in raw_error.lower():
                return "No ejecuté la acción correctamente porque falta información requerida (required)."
            return "No ejecuté la acción correctamente. Revisa los detalles antes de volver a intentarlo."
        if not result.tool_result:
            return "No se ejecutó ninguna acción porque el plan no produjo un resultado verificable."
        verified = self.format_verified_result(intent.target, result.tool_result.data)
        if verified:
            return verified
        tool_id = result.tool_result.tool_id or intent.target
        return f"La acción terminó correctamente y fue confirmada por {tool_id}."

    @staticmethod
    def format_verified_result(target: str, data: Any) -> Optional[str]:
        if not isinstance(data, dict):
            return None

        def gib(value: Any) -> str:
            try:
                return f"{float(value) / (1024**3):.1f} GB"
            except (TypeError, ValueError):
                return "—"

        if target == "system.memory" and "percent" in data:
            return (
                f"Tu PC está usando {data['percent']:.1f}% de la RAM: "
                f"{gib(data.get('used'))} de {gib(data.get('total'))}. "
                f"Quedan {gib(data.get('available'))} disponibles."
            )
        if target == "system.cpu" and "percent" in data:
            cores = data.get("cores") or data.get("logical_cores")
            suffix = f" en {cores} núcleos lógicos" if cores else ""
            return f"El procesador está usando {data['percent']:.1f}%{suffix}."
        if target == "system.disk" and "percent" in data:
            return (
                f"El disco está usando {data['percent']:.1f}%: "
                f"{gib(data.get('used'))} usados y {gib(data.get('free'))} libres."
            )
        if target == "app.discovery" and isinstance(data.get("apps"), list):
            count = len(data["apps"])
            return (
                f"Encontré {count} aplicaciones disponibles en las ubicaciones verificadas."
                if count
                else "No encontré aplicaciones ejecutables en las ubicaciones verificadas."
            )
        if target in {"system.info", "system.health"} and isinstance(data.get("memory"), dict):
            cpu = data.get("cpu", {})
            memory = data.get("memory", {})
            disk = data.get("disk", {})
            cpu_percent = float(cpu.get("percent", 0))
            memory_percent = float(memory.get("percent", 0))
            disk_percent = float(disk.get("percent", 0))
            risks = []
            if cpu_percent >= 90:
                risks.append("CPU en nivel crítico")
            elif cpu_percent >= 75:
                risks.append("CPU con carga alta")
            if memory_percent >= 90:
                risks.append("RAM en nivel crítico")
            elif memory_percent >= 80:
                risks.append("RAM con presión alta")
            if disk_percent >= 95:
                risks.append("disco casi lleno")
            elif disk_percent >= 85:
                risks.append("poco espacio libre en disco")
            measured = (
                f"CPU {cpu_percent:.1f}%, RAM {memory_percent:.1f}% y disco {disk_percent:.1f}%. "
                f"Memoria disponible: {gib(memory.get('available'))}; espacio libre: {gib(disk.get('free'))}."
            )
            if target == "system.health":
                assessment = (
                    "Riesgos detectados: " + "; ".join(risks) + "."
                    if risks
                    else "No detecté presión crítica de CPU, RAM o disco."
                )
                return f"Diagnóstico del equipo: {measured} {assessment}"
            return f"Estado actual: {measured}"
        if target == "executor.launch" and data.get("elevation_requested"):
            return "Windows recibió la solicitud. Debes aceptar el aviso de administrador para continuar."
        if target == "executor.launch" and data.get("success"):
            return f"Windows inició {data.get('app', 'la aplicación')}."
        return None

    @staticmethod
    def _status(result: Any) -> str:
        if getattr(result, "blocked", False):
            return "needs_approval"
        if getattr(result, "simulated", False):
            return "preview"
        if getattr(result, "error", None):
            return "failed"
        if getattr(result, "approved", False):
            return "completed"
        return "not_executed"

    @staticmethod
    def _title(status: str) -> str:
        return {
            "completed": "Acción completada",
            "needs_approval": "Necesita tu aprobación",
            "preview": "Vista previa lista",
            "failed": "No se pudo completar",
            "not_executed": "No se realizó ninguna acción",
        }[status]

    @staticmethod
    def _risk_level(score: Optional[float]) -> str:
        if score is None:
            return "unknown"
        if score >= 0.8:
            return "critical"
        if score >= 0.6:
            return "high"
        if score >= 0.3:
            return "medium"
        return "low"

    @staticmethod
    def _next_action(result: Any, status: str) -> Optional[str]:
        if status == "needs_approval":
            return "Revisa el impacto y decide si deseas autorizar la acción."
        if status == "failed":
            return "Abre los detalles para revisar la causa y vuelve a intentarlo cuando esté resuelta."
        if status == "preview":
            return "Revisa el plan. La vista previa no modificó tu equipo."
        return None

    @staticmethod
    def _details(result: Any) -> Dict[str, Any]:
        intent = result.plan.intent
        decision = result.decision
        return {
            "intent": {
                "action": intent.action,
                "target": intent.target,
                "confidence": intent.confidence,
            },
            "decision": {
                "value": decision.decision,
                "reason": decision.reason,
            }
            if decision
            else None,
            "tools": [step.tool_id for step in result.plan.plan.steps],
            "error": result.error,
        }
