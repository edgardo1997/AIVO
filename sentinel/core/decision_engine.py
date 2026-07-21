from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging

from .planner import Plan
from .intent import Intent
from .objective_risk_assessor import ObjectiveRiskAssessor, ObjectiveRiskAssessment
from .simulation import SimulatedImpact, SimulationResult

logger = logging.getLogger(__name__)


class Decision(str):
    APPROVE = "approve"
    REJECT = "reject"
    REQUIRE_CONFIRM = "require_confirm"
    MODIFY = "modify"


@dataclass
class DecisionResult:
    decision: Decision
    plan: Plan
    reason: str
    modifications: Optional[List[str]] = None
    suggested_alternative: Optional[str] = None
    context_factors: List[str] = field(default_factory=list)
    base_risk_score: float = 0.0
    context_modifier: float = 0.0
    final_risk_score: float = 0.0


IMPACT_THRESHOLDS = {
    "view": {"auto": 0.0, "confirm": 0.1},
    "confirm": {"auto": 0.3, "confirm": 0.7},
    "auto": {"auto": 0.6, "confirm": 0.9},
    "admin": {"auto": 1.0, "confirm": 1.0},
}

CONTEXT_MODIFIERS: Dict[str, float] = {
    "cpu_critical": 0.10,
    "memory_critical": 0.15,
    "disk_critical": 0.10,
    "many_processes": 0.05,
}


def _extract_context_factors(context: Dict[str, Any]) -> List[str]:
    factors: List[str] = []
    summary = context.get("system_summary", {})
    if not summary:
        return factors

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

    return factors


class DecisionEngine:
    def __init__(
        self,
        auto_approve_threshold: float = 0.3,
        require_confirm_threshold: float = 0.6,
        get_permission_level=None,
        model_router=None,
        enable_llm_advisor: bool = True,
    ):
        self._auto_approve = auto_approve_threshold
        self._require_confirm = require_confirm_threshold
        self._get_level = get_permission_level or (lambda: "confirm")
        self._model_router = model_router

        # Objective risk assessment (no LLM involvement — LLM has zero authority)
        self._objective_assessor = ObjectiveRiskAssessor()

    def set_model_router(self, router) -> None:
        self._model_router = router

    def set_enable_llm_advisor(self, enabled: bool) -> None:
        pass

    @staticmethod
    def _simulation_risk_overrides(
        sim_result: SimulationResult, final_risk: float, power_level: str
    ) -> tuple[float, Optional[str]]:
        overall_risk = sim_result.overall_risk
        has_irreversible = any(i.irreversible for i in sim_result.impacts)
        forced_decision = None

        if overall_risk == "critical" and has_irreversible:
            if power_level != "admin":
                forced_decision = Decision.REJECT
            final_risk = min(final_risk + 0.5, 1.0)
        elif overall_risk == "critical":
            if power_level != "admin":
                forced_decision = Decision.REQUIRE_CONFIRM
            final_risk = min(final_risk + 0.3, 1.0)
        elif overall_risk == "high":
            if power_level != "admin":
                forced_decision = Decision.REQUIRE_CONFIRM
            final_risk = min(final_risk + 0.2, 1.0)
        elif overall_risk == "medium":
            if power_level != "admin":
                forced_decision = Decision.REQUIRE_CONFIRM
            final_risk = min(final_risk + 0.1, 1.0)
        elif overall_risk == "low":
            final_risk = max(final_risk - 0.1, 0.0)

        return final_risk, forced_decision

    def evaluate(
        self,
        plan: Plan,
        context: Optional[Dict[str, Any]] = None,
        simulation_result: Optional[SimulationResult] = None,
    ) -> DecisionResult:
        # Evaluación OBJETIVA del riesgo — el LLM no participa en decisiones
        level = self._get_level()
        if (context or {}).get("_orchestrator_approval"):
            level = "admin"

        objective_assessment = self._objective_assessor.assess(
            plan,
            context,
            permission_level=level
        )

        if level == "view" and any(
            step.estimated_impact not in ("low",) for step in plan.steps
        ):
            return DecisionResult(
                decision=Decision.REJECT,
                plan=plan,
                reason="Read-only permission level cannot execute system modifications.",
                context_factors=objective_assessment.context_factors,
                base_risk_score=objective_assessment.base_risk,
                context_modifier=objective_assessment.context_modifier,
                final_risk_score=objective_assessment.final_risk,
            )

        # Use typed SimulationResult if available; fall back to context dict
        if simulation_result:
            final_risk, forced_decision = self._simulation_risk_overrides(
                simulation_result,
                objective_assessment.final_risk,
                level
            )
            if forced_decision:
                return self._create_forced_decision_result(
                    forced_decision,
                    plan,
                    objective_assessment,
                    simulation_result,
                    level
                )
        elif (context or {}).get("simulation"):
            sim_dict = context["simulation"]
            fallback_impacts = []
            if sim_dict.get("has_irreversible"):
                fallback_impacts.append(SimulatedImpact(
                    step_id="", tool_id="", description="",
                    impact_type="system", impact_level="critical",
                    estimated_duration_ms=0, irreversible=True,
                ))
            sim_result = SimulationResult(
                plan_id="",
                impacts=fallback_impacts,
                pre_snapshot={},
                overall_risk=sim_dict.get("overall_risk", "low"),
                requires_confirmation=sim_dict.get("requires_confirmation", False),
                summary=sim_dict.get("summary", ""),
            )
            final_risk, forced_decision = self._simulation_risk_overrides(
                sim_result,
                objective_assessment.final_risk,
                level
            )
            if forced_decision:
                return self._create_forced_decision_result(
                    forced_decision,
                    plan,
                    objective_assessment,
                    sim_result,
                    level
                )

        if level != "admin":
            if objective_assessment.should_reject_by_objective:
                return DecisionResult(
                    decision=Decision.REJECT,
                    plan=plan,
                    reason=f"Objective risk assessment rejected plan (risk={objective_assessment.final_risk:.2f}). Sources: {objective_assessment.data_sources}",
                    context_factors=objective_assessment.context_factors,
                    base_risk_score=objective_assessment.base_risk,
                    context_modifier=objective_assessment.context_modifier,
                    final_risk_score=objective_assessment.final_risk,
                )

            if objective_assessment.requires_confirmation_by_objective:
                return DecisionResult(
                    decision=Decision.REQUIRE_CONFIRM,
                    plan=plan,
                    reason=f"Objective risk assessment requires confirmation (risk={objective_assessment.final_risk:.2f}). Sources: {objective_assessment.data_sources}.",
                    context_factors=objective_assessment.context_factors,
                    base_risk_score=objective_assessment.base_risk,
                    context_modifier=objective_assessment.context_modifier,
                    final_risk_score=objective_assessment.final_risk,
                )

        # Paso 6: Auto-approve si riesgo es bajo según evaluación OBJETIVA
        return DecisionResult(
            decision=Decision.APPROVE,
            plan=plan,
            reason=f"Auto-approved by objective risk assessment (risk={objective_assessment.final_risk:.2f}). Sources: {objective_assessment.data_sources}",
            context_factors=objective_assessment.context_factors,
            base_risk_score=objective_assessment.base_risk,
            context_modifier=objective_assessment.context_modifier,
            final_risk_score=objective_assessment.final_risk,
        )

    async def evaluate_async(
        self,
        plan: Plan,
        context: Optional[Dict[str, Any]] = None,
        simulation_result: Optional[SimulationResult] = None,
    ) -> DecisionResult:
        """Evaluate objectively with zero LLM authority.

        The decision is purely objective — no model is called during evaluation.
        LLM advisory (if any) only runs post-execution in the Advisory layer,
        where it can observe outcomes without affecting authorization.
        """
        return self.evaluate(plan, context, simulation_result=simulation_result)

    def _create_forced_decision_result(
        self,
        forced_decision: str,
        plan: Plan,
        objective_assessment: ObjectiveRiskAssessment,
        sim_result: SimulationResult,
        level: str
    ) -> DecisionResult:
        if forced_decision == Decision.REJECT:
            return DecisionResult(
                decision=Decision.REJECT,
                plan=plan,
                reason=f"Simulation detected critical+irreversible risk. {sim_result.summary}. Objective risk: {objective_assessment.final_risk:.2f}",
                context_factors=objective_assessment.context_factors,
                base_risk_score=objective_assessment.base_risk,
                context_modifier=objective_assessment.context_modifier,
                final_risk_score=objective_assessment.final_risk,
            )
        elif forced_decision == Decision.REQUIRE_CONFIRM:
            return DecisionResult(
                decision=Decision.REQUIRE_CONFIRM,
                plan=plan,
                reason=f"Simulation risk '{sim_result.overall_risk}' requires confirmation. {sim_result.summary}. Objective risk: {objective_assessment.final_risk:.2f}",
                context_factors=objective_assessment.context_factors,
                base_risk_score=objective_assessment.base_risk,
                context_modifier=objective_assessment.context_modifier,
                final_risk_score=objective_assessment.final_risk,
            )
        else:
            return DecisionResult(
                decision=Decision.APPROVE,
                plan=plan,
                reason=f"Auto-approved (risk={objective_assessment.final_risk:.2f}, level={level}).",
                context_factors=objective_assessment.context_factors,
                base_risk_score=objective_assessment.base_risk,
                context_modifier=objective_assessment.context_modifier,
                final_risk_score=objective_assessment.final_risk,
            )

    def should_skip_decision(self, intent: Intent) -> bool:
        read_only_analysis_targets = {
            "system.health",
            "system.info",
            "system.cpu",
            "system.memory",
            "system.disk",
            "system.network",
            "system.processes",
            "system.gpu",
            "app.discovery",
        }
        return intent.confidence > 0.5 and (
            intent.action == "query"
            or (intent.action == "analyze" and intent.target in read_only_analysis_targets)
            or (intent.action == "execute" and intent.target in read_only_analysis_targets)
        )
