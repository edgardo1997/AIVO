from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging

from .planner import Plan
from .intent import Intent

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


DECISION_LLM_PROMPT = """You are a risk assessor for a system orchestration platform called Sentinel.
Given a plan with steps and current system context, evaluate the risk of executing this plan.

Analyze:
1. What each step does
2. Whether steps are destructive or irreversible
3. Current system stress (high CPU, memory, disk)
4. Whether this is a good time to execute

Return ONLY valid JSON:
{"risk_modifier": -0.2 to 0.3, "reason": "brief justification", "warnings": []}
Positive modifier = higher risk, negative = lower risk."""


class DecisionEngine:
    def __init__(
        self,
        auto_approve_threshold: float = 0.3,
        require_confirm_threshold: float = 0.6,
        get_permission_level=None,
        model_router=None,
    ):
        self._auto_approve = auto_approve_threshold
        self._require_confirm = require_confirm_threshold
        self._get_level = get_permission_level or (lambda: "confirm")
        self._model_router = model_router

    def set_model_router(self, router) -> None:
        self._model_router = router

    def _simulation_risk_overrides(
        self, sim: Dict[str, Any], final_risk: float, power_level: str
    ) -> tuple[float, Optional[str]]:
        overall_risk = sim.get("overall_risk", "low")
        has_irreversible = sim.get("has_irreversible", False)
        forced_decision = None

        if overall_risk == "critical" and has_irreversible:
            forced_decision = Decision.REJECT
            final_risk = min(final_risk + 0.5, 1.0)
        elif overall_risk == "critical":
            forced_decision = Decision.REQUIRE_CONFIRM
            final_risk = min(final_risk + 0.3, 1.0)
        elif overall_risk == "high":
            forced_decision = Decision.REQUIRE_CONFIRM
            final_risk = min(final_risk + 0.2, 1.0)
        elif overall_risk == "medium":
            if power_level != "admin":
                forced_decision = Decision.REQUIRE_CONFIRM
            final_risk = min(final_risk + 0.1, 1.0)
        elif overall_risk == "low":
            final_risk = max(final_risk - 0.1, 0.0)

        return final_risk, forced_decision

    def evaluate(self, plan: Plan, context: Optional[Dict[str, Any]] = None) -> DecisionResult:
        base_risk = plan.risk_score
        level = self._get_level()
        context_factors = _extract_context_factors(context or {})

        context_modifier = sum(CONTEXT_MODIFIERS.get(f, 0.0) for f in context_factors)
        final_risk = min(base_risk + context_modifier, 1.0)

        level_thresholds = IMPACT_THRESHOLDS.get(level, IMPACT_THRESHOLDS["confirm"])
        auto_max = level_thresholds["auto"]
        confirm_max = level_thresholds["confirm"]

        irreversible_high_risk = any(
            s.estimated_impact in ("high", "critical") and not s.is_reversible for s in plan.steps
        )

        sim = (context or {}).get("simulation")
        forced_decision = None
        if sim:
            final_risk, forced_decision = self._simulation_risk_overrides(sim, final_risk, level)

        if forced_decision is None and (final_risk > auto_max or irreversible_high_risk):
            llm_assessment = self._assess_risk_with_llm(plan, context)
            if llm_assessment:
                modifier = llm_assessment.get("risk_modifier", 0)
                old_risk = final_risk
                final_risk = min(max(final_risk + modifier, 0.0), 1.0)
                context_modifier = final_risk - base_risk
                logger.info(
                    "LLM risk adjustment: %.2f -> %.2f (modifier=%.2f): %s",
                    old_risk,
                    final_risk,
                    modifier,
                    llm_assessment.get("reason", ""),
                )

        factors_str = f" | context={context_factors}" if context_factors else ""
        sim_str = f" | sim={sim.get('overall_risk', '')}" if sim else ""

        if forced_decision == Decision.REJECT:
            logger.info(
                "Plan REJECTED by simulation: risk=%s irreversible=%s level=%s%s%s",
                sim.get("overall_risk"),
                sim.get("has_irreversible"),
                level,
                factors_str,
                sim_str,
            )
            return DecisionResult(
                decision=Decision.REJECT,
                plan=plan,
                reason=f"Simulation detected critical+irreversible risk. {sim.get('summary', '')}",
                context_factors=context_factors,
                base_risk_score=base_risk,
                context_modifier=context_modifier,
                final_risk_score=final_risk,
            )

        if forced_decision == Decision.REQUIRE_CONFIRM:
            logger.info(
                "Plan requires confirmation (simulation): risk=%s level=%s%s%s",
                sim.get("overall_risk"),
                level,
                factors_str,
                sim_str,
            )
            return DecisionResult(
                decision=Decision.REQUIRE_CONFIRM,
                plan=plan,
                reason=f"Simulation risk '{sim.get('overall_risk')}' requires confirmation. {sim.get('summary', '')}",
                context_factors=context_factors,
                base_risk_score=base_risk,
                context_modifier=context_modifier,
                final_risk_score=final_risk,
            )

        if final_risk <= auto_max and (not irreversible_high_risk or level == "admin"):
            logger.info(
                "Plan auto-approved: base=%.2f mod=%.2f final=%.2f level=%s%s%s",
                base_risk,
                context_modifier,
                final_risk,
                level,
                factors_str,
                sim_str,
            )
            return DecisionResult(
                decision=Decision.APPROVE,
                plan=plan,
                reason=f"Auto-approved (risk={final_risk:.2f}, level={level}).",
                context_factors=context_factors,
                base_risk_score=base_risk,
                context_modifier=context_modifier,
                final_risk_score=final_risk,
            )

        if final_risk <= confirm_max:
            logger.info(
                "Plan requires confirmation: base=%.2f mod=%.2f final=%.2f level=%s%s%s",
                base_risk,
                context_modifier,
                final_risk,
                level,
                factors_str,
                sim_str,
            )
            return DecisionResult(
                decision=Decision.REQUIRE_CONFIRM,
                plan=plan,
                reason=f"Risk score {final_risk:.2f} requires confirmation at level '{level}'.",
                context_factors=context_factors,
                base_risk_score=base_risk,
                context_modifier=context_modifier,
                final_risk_score=final_risk,
            )

        logger.info(
            "Plan REJECTED: base=%.2f mod=%.2f final=%.2f > confirm_max=%.2f level=%s%s%s",
            base_risk,
            context_modifier,
            final_risk,
            confirm_max,
            level,
            factors_str,
            sim_str,
        )
        return DecisionResult(
            decision=Decision.REJECT,
            plan=plan,
            reason=f"Risk score {final_risk:.2f} exceeds maximum for level '{level}'.",
            context_factors=context_factors,
            base_risk_score=base_risk,
            context_modifier=context_modifier,
            final_risk_score=final_risk,
        )

    def _assess_risk_with_llm(self, plan: Plan, context: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        from .model_router import TaskType

        if not self._model_router:
            return None
        if not hasattr(self._model_router, "_key_map") or not self._model_router._key_map:
            return None
        try:
            steps_text = "\n".join(
                f"  - {s.tool_id}: {s.description} (impact={s.estimated_impact}, reversible={s.is_reversible})"
                for s in plan.steps
            )
            context_text = ""
            if context:
                summary = context.get("system_summary", {})
                if summary:
                    context_text = f"\nSystem: cpu={summary.get('cpu_percent')}% mem={summary.get('memory_percent')}% disk={summary.get('disk_percent')}%"
            messages = [
                {"role": "system", "content": DECISION_LLM_PROMPT + context_text},
                {"role": "user", "content": f"Plan steps:\n{steps_text}\n\nBase risk: {plan.risk_score}"},
            ]
            result = self._model_router.chat(messages, task_type=TaskType.ANALYSIS)
            import json

            text = result["response"].strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3].strip()
            return json.loads(text)
        except Exception as e:
            logger.warning("LLM risk assessment failed: %s", e)
            return None

    def should_skip_decision(self, intent: Intent) -> bool:
        return intent.action in ("query",) and intent.confidence > 0.5
