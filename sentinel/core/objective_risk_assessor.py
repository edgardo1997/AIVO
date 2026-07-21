"""Objective Risk Assessor: Evaluación de riesgo basada en factores objetivos.

Este componente evalúa el riesgo basado únicamente en factores objetivos:
- Estado del sistema (CPU, RAM, disco)
- Irreversibilidad de acciones
- Nivel de permisos del usuario
- Resultados de simulación

NO usa el LLM para decisiones de seguridad.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .planner import Plan

logger = logging.getLogger(__name__)


@dataclass
class ObjectiveRiskAssessment:
    """Evaluación de riesgo basada en factores objetivos"""
    base_risk: float
    context_factors: List[str]
    context_modifier: float
    simulation_modifier: float
    final_risk: float
    is_irreversible: bool
    requires_confirmation_by_objective: bool
    should_reject_by_objective: bool
    data_sources: List[str]


class ObjectiveRiskAssessor:
    """Evaluador de riesgo basado en factores objetivos"""

    # Modificadores de contexto basados en estado del sistema
    CONTEXT_MODIFIERS: Dict[str, float] = {
        "cpu_critical": 0.10,
        "memory_critical": 0.15,
        "disk_critical": 0.10,
        "many_processes": 0.05,
        "new_app_detected": 0.08,
        "app_removed": 0.05,
        "app_capabilities_changed": 0.10,
        "hardware_changed": 0.12,
        "gpu_unavailable": 0.15,
        "gpu_low_vram": 0.10,
        "app_not_found": 0.08,
        "app_low_confidence": 0.05,
    }

    # Map environmental change types to context factor names
    _ENV_CHANGE_FACTORS: Dict[str, str] = {
        "application_added": "new_app_detected",
        "application_removed": "app_removed",
        "application_capabilities_changed": "app_capabilities_changed",
        "hardware_capacity_changed": "hardware_changed",
    }

    # Umbrales de impacto por nivel de permisos
    IMPACT_THRESHOLDS = {
        "view": {"auto": 0.0, "confirm": 0.1},
        "confirm": {"auto": 0.3, "confirm": 0.7},
        "auto": {"auto": 0.6, "confirm": 0.9},
        "admin": {"auto": 1.0, "confirm": 1.0},
    }

    def __init__(self):
        pass

    def assess(
        self,
        plan: Plan,
        context: Optional[Dict[str, Any]] = None,
        permission_level: str = "confirm"
    ) -> ObjectiveRiskAssessment:
        """Evalúa el riesgo basado en factores objetivos

        Args:
            plan: Plan a evaluar
            context: Contexto del sistema
            permission_level: Nivel de permisos del usuario

        Returns:
            ObjectiveRiskAssessment con evaluación basada en factores objetivos
        """
        data_sources = ["plan_risk_score"]

        # Paso 1: Riesgo base del plan
        base_risk = plan.risk_score

        # Paso 2: Extraer factores de contexto del sistema
        context_factors = self._extract_context_factors(context or {}, plan=plan)
        data_sources.append("system_context")
        if any(f in self._ENV_CHANGE_FACTORS.values() for f in context_factors):
            data_sources.append("environment_learning")

        # Paso 3: Calcular modificador de contexto
        context_modifier = sum(
            self.CONTEXT_MODIFIERS.get(f, 0.0) for f in context_factors
        )

        # Paso 4: Detectar acciones irreversibles
        is_irreversible = any(
            s.estimated_impact in ("high", "critical") and not s.is_reversible
            for s in plan.steps
        )
        data_sources.append("step_analysis")

        # Paso 5: Aplicar modificador de simulación si está disponible
        simulation_modifier = 0.0
        sim = (context or {}).get("simulation")
        if sim:
            simulation_modifier, sim_decision = self._assess_simulation_risk(sim, permission_level)
            data_sources.append("simulation")

        # Paso 6: Calcular riesgo final
        final_risk = min(base_risk + context_modifier + simulation_modifier, 1.0)
        final_risk = max(final_risk, 0.0)  # Asegurar que no sea negativo

        # Paso 7: Determinar si requiere confirmación basado en factores objetivos
        level_thresholds = self.IMPACT_THRESHOLDS.get(
            permission_level,
            self.IMPACT_THRESHOLDS["confirm"]
        )
        auto_max = level_thresholds["auto"]
        confirm_max = level_thresholds["confirm"]

        requires_confirmation_by_objective = (
            final_risk > auto_max or
            (is_irreversible and permission_level != "admin")
        )

        # Paso 8: Determinar si debe rechazar basado en factores objetivos
        critical_irreversible_simulation = bool(
            sim
            and sim.get("overall_risk") == "critical"
            and sim.get("has_irreversible")
        )
        should_reject_by_objective = bool(
            final_risk > confirm_max
            or (critical_irreversible_simulation and not is_irreversible)
        )

        return ObjectiveRiskAssessment(
            base_risk=base_risk,
            context_factors=context_factors,
            context_modifier=context_modifier,
            simulation_modifier=simulation_modifier,
            final_risk=final_risk,
            is_irreversible=is_irreversible,
            requires_confirmation_by_objective=requires_confirmation_by_objective,
            should_reject_by_objective=should_reject_by_objective,
            data_sources=data_sources
        )

    def _extract_context_factors(self, context: Dict[str, Any], plan: Optional[Plan] = None) -> List[str]:
        """Extrae factores de riesgo del contexto del sistema y cambios ambientales."""
        factors: List[str] = []
        summary = context.get("system_summary", {})

        if summary:
            cpu = summary.get("cpu_percent")
            if cpu is not None:
                if cpu > 90:
                    factors.append("cpu_critical")
                elif cpu > 70:
                    factors.append("cpu_high")

            mem = summary.get("memory_percent")
            if mem is not None:
                if mem > 90:
                    factors.append("memory_critical")
                elif mem > 75:
                    factors.append("memory_high")

            disk = summary.get("disk_percent")
            if disk is not None:
                if disk > 95:
                    factors.append("disk_critical")
                elif disk > 85:
                    factors.append("disk_high")

            procs = summary.get("process_count")
            if procs is not None and procs > 200:
                factors.append("many_processes")

        # Environmental change factors (read change_type only — safe enum, not app names)
        env_changes = context.get("environment_changes", [])
        if env_changes:
            seen: set = set()
            for change in env_changes:
                factor = self._ENV_CHANGE_FACTORS.get(change.get("change_type", ""))
                if factor and factor not in seen:
                    factors.append(factor)
                    seen.add(factor)

        # Hardware state factors — read directly from deep_context
        deep_ctx = context.get("deep_context", {})
        if isinstance(deep_ctx, dict):
            hardware = deep_ctx.get("hardware", {})
            if isinstance(hardware, dict):
                gpu_avail = hardware.get("gpu_available")
                if gpu_avail is False:
                    factors.append("gpu_unavailable")
                vram = hardware.get("gpu_vram_gb")
                if vram is not None and isinstance(vram, (int, float)) and vram < 4:
                    factors.append("gpu_low_vram")

            # App confidence factors
            installed_apps = deep_ctx.get("installed_apps", [])
            if isinstance(installed_apps, list) and plan:
                for step in plan.steps:
                    app_name = step.params.get("app") or step.params.get("name") or ""
                    if not app_name:
                        continue
                    from .planner import Planner
                    evidence = Planner._application_evidence(context, app_name, installed_apps)
                    if evidence is None:
                        factors.append("app_not_found")
                    else:
                        conf = float(evidence.get("confidence", 0.0) or 0.0)
                        if conf > 0 and conf < 0.7:
                            factors.append("app_low_confidence")

        return factors

    def _assess_simulation_risk(
        self,
        sim: Dict[str, Any],
        permission_level: str
    ) -> tuple[float, Optional[str]]:
        """Evalúa el riesgo basado en simulación"""
        overall_risk = sim.get("overall_risk", "low")
        has_irreversible = sim.get("has_irreversible", False)

        modifier = 0.0

        if overall_risk == "critical" and has_irreversible:
            modifier = 0.5  # Incremento muy alto
        elif overall_risk == "critical":
            modifier = 0.3  # Incremento alto
        elif overall_risk == "high":
            modifier = 0.2  # Incremento medio
        elif overall_risk == "medium":
            if permission_level != "admin":
                modifier = 0.1  # Incremento bajo para usuarios no admin
        elif overall_risk == "low":
            modifier = -0.1  # Reducción si riesgo es bajo

        return modifier, None
