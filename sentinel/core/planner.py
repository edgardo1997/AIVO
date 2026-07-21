import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging

from .intent import Intent
from .capability_registry import Capability, CapabilityRegistry, RiskLevel
from .goals import GoalDefinition, GoalRegistry, GoalScorer, GoalScorerConfig
from .model_router import RouterDecision
from .recovery import RecoveryPolicy
from .application_knowledge import AppProfile, get_application_knowledge
from .event_bus import EventBus
from .events import SentinelEvent
from . import event_types

logger = logging.getLogger(__name__)


@dataclass
class PlanStep:
    id: str
    tool_id: str
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    is_reversible: bool = False
    rollback_tool_id: Optional[str] = None
    rollback_params: Optional[Dict[str, Any]] = None
    estimated_impact: str = "low"
    estimated_duration_ms: Optional[float] = None
    depends_on: List[str] = field(default_factory=list)
    recovery_policy: Optional[Any] = None
    model_decision: Optional[RouterDecision] = None


@dataclass
class Plan:
    steps: List[PlanStep]
    intent: Intent
    risk_score: float = 0.0
    estimated_duration_ms: Optional[float] = None
    description: str = ""
    goal: Optional[GoalDefinition] = None


ROLLBACK_MAP: Dict[str, tuple[str, Optional[Dict[str, str]]]] = {
    "filesystem.write": ("filesystem.undo_write", {"original_content": "original_content"}),
    "filesystem.delete": ("filesystem.restore", None),
    "executor.kill": ("executor.restart", {"pid": "pid", "process_name": "process_name"}),
}

STEP_DEFINITIONS: Dict[str, List[PlanStep]] = {
    "system.cpu": [
        PlanStep(id="cpu", tool_id="system.cpu", description="Get CPU usage", estimated_impact="low"),
    ],
    "system.memory": [
        PlanStep(id="mem", tool_id="system.info", description="Get memory usage", estimated_impact="low"),
    ],
    "system.disk": [
        PlanStep(id="disk", tool_id="system.info", description="Get disk usage", estimated_impact="low"),
    ],
    "system.processes": [
        PlanStep(id="procs", tool_id="system.processes", description="Get process list", estimated_impact="low"),
    ],
    "system.network": [
        PlanStep(id="net", tool_id="system.info", description="Get network info", estimated_impact="low"),
    ],
    "system.info": [
        PlanStep(id="sys", tool_id="system.info", description="Get full system info", estimated_impact="low"),
    ],
    "system.health": [
        PlanStep(id="cpu", tool_id="system.cpu", description="Get CPU usage", estimated_impact="low"),
        PlanStep(id="mem", tool_id="system.info", description="Get memory usage", estimated_impact="low"),
        PlanStep(id="disk", tool_id="system.info", description="Get disk usage", estimated_impact="low"),
        PlanStep(
            id="procs",
            tool_id="system.processes",
            description="Get top processes",
            # Health analysis ranks CPU consumers; skipping per-process memory
            # avoids slow protected-process queries. Explicit process listings
            # still include memory by default.
            params={"limit": 5, "include_memory": False},
            estimated_impact="low",
            depends_on=["mem", "disk"],
        ),
    ],
    "system.uptime": [
        PlanStep(id="sys", tool_id="system.info", description="Get uptime info", estimated_impact="low"),
    ],
    "app.discovery": [
        PlanStep(
            id="apps",
            tool_id="app.discovery",
            params={"action": "list", "limit": 30},
            description="Discover installed applications available to Sentinel",
            estimated_impact="low",
        ),
    ],
    "models.list": [
        PlanStep(id="models", tool_id="system.info", description="List available models", estimated_impact="low"),
    ],
    "settings.ai": [
        PlanStep(id="cfg", tool_id="system.info", description="AI configuration", estimated_impact="low"),
    ],
    "executor.command": [
        PlanStep(
            id="exec",
            tool_id="executor.command",
            description="Execute command",
            estimated_impact="medium",
            is_reversible=False,
        ),
    ],
    "executor.launch": [
        PlanStep(
            id="check",
            tool_id="system.processes",
            description="Check if already running",
            params={"limit": 5},
            estimated_impact="low",
        ),
        PlanStep(
            id="launch",
            tool_id="executor.launch",
            description="Launch process",
            estimated_impact="medium",
            is_reversible=True,
            rollback_tool_id="executor.kill",
            depends_on=["check"],
        ),
    ],
    "executor.kill": [
        PlanStep(id="find", tool_id="system.processes", description="Find process by name", estimated_impact="low"),
        PlanStep(
            id="kill",
            tool_id="executor.kill",
            description="Kill process",
            estimated_impact="medium",
            is_reversible=True,
            rollback_tool_id="executor.restart",
            depends_on=["find"],
        ),
    ],
    "filesystem.search": [
        PlanStep(
            id="locate",
            tool_id="filesystem.search",
            description="Search files matching pattern",
            estimated_impact="low",
        ),
    ],
    "filesystem.write": [
        PlanStep(
            id="write",
            tool_id="filesystem.write",
            description="Write content to file",
            estimated_impact="high",
            is_reversible=True,
            rollback_tool_id="filesystem.undo_write",
        ),
    ],
    "filesystem.delete": [
        PlanStep(
            id="del",
            tool_id="filesystem.delete",
            description="Delete file (movable to temp)",
            estimated_impact="high",
            is_reversible=True,
            rollback_tool_id="filesystem.restore",
        ),
    ],
}


class Planner:
    def __init__(
        self,
        step_definitions: Optional[Dict[str, List[PlanStep]]] = None,
        capability_registry: Optional[CapabilityRegistry] = None,
        goal_registry: Optional[GoalRegistry] = None,
        scorer_config: Optional[GoalScorerConfig] = None,
        event_bus: Optional[EventBus] = None,
    ):
        self._definitions = step_definitions or STEP_DEFINITIONS
        self._capability_registry = capability_registry
        self._goal_registry = goal_registry
        self._scorer_config = scorer_config
        self._event_bus = event_bus

    def set_event_bus(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    def _emit(self, event_type: str, *, session_id: str = "", request_id: str = "", status: str = "", details: Optional[Dict[str, Any]] = None) -> None:
        if self._event_bus is None:
            return
        event = SentinelEvent.new(
            event_type=event_type,
            session_id=session_id or "",
            request_id=request_id or "",
            component="planner",
            status=status,
            details=details,
        )
        asyncio.ensure_future(self._event_bus.emit(event))

    def _step_from_capability(self, cap: Capability) -> PlanStep:
        impact_map = {
            RiskLevel.LOW: "low",
            RiskLevel.MEDIUM: "medium",
            RiskLevel.HIGH: "high",
            RiskLevel.CRITICAL: "critical",
        }
        has_rollback = cap.id in ROLLBACK_MAP
        is_reversible = (
            True
            if has_rollback
            else (cap.reversible if cap.reversible is not None else cap.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM))
        )
        rollback_tool_id = None
        rollback_params = None
        if has_rollback:
            rb_tool_id, rb_param_map = ROLLBACK_MAP[cap.id]
            rollback_tool_id = rb_tool_id
            if rb_param_map:
                rollback_params = dict(rb_param_map)
        return PlanStep(
            id=cap.id.rsplit(".", 1)[-1],
            tool_id=cap.id,
            params=dict(cap.default_parameters),
            description=cap.description or cap.name,
            estimated_impact=cap.estimated_impact or impact_map.get(cap.risk_level, "medium"),
            is_reversible=is_reversible,
            rollback_tool_id=rollback_tool_id,
            rollback_params=rollback_params,
        )

    def _goal_risk_score(self, goal: GoalDefinition) -> float:
        return {"low": 0.1, "medium": 0.4, "high": 0.7, "critical": 1.0}.get(goal.base_risk.value, 0.3)

    def plan(self, intent: Intent, context: Optional[Dict[str, Any]] = None, app_profiles: Optional[List[Dict[str, Any]]] = None) -> Plan:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("execution_id", "")
        self._emit(event_types.PLANNER_STARTED, session_id=sid, request_id=rid)
        target = intent.target

        goal = None
        if self._goal_registry is not None:
            candidates = self._goal_registry.find_candidates(target)
            if candidates:
                scorer = GoalScorer(context, config=self._scorer_config)
                ranked = scorer.rank(candidates)
                if ranked:
                    goal = ranked[0].result.goal

        cap = None
        if self._capability_registry is not None:
            cap = self._capability_registry.get(target)

        if cap is not None:
            steps_def = [self._step_from_capability(cap)]
        else:
            steps_def = self._definitions.get(target)

        if not steps_def:
            steps_def = [
                PlanStep(
                    id="default", tool_id="system.info", description=f"Process {target}", estimated_impact="medium"
                ),
            ]

        steps = []
        for sdef in steps_def:
            step = PlanStep(
                id=sdef.id,
                tool_id=sdef.tool_id,
                params=dict(sdef.params),
                description=sdef.description,
                is_reversible=sdef.is_reversible,
                rollback_tool_id=sdef.rollback_tool_id,
                rollback_params=sdef.rollback_params,
                estimated_impact=sdef.estimated_impact,
                depends_on=list(sdef.depends_on),
                recovery_policy=sdef.recovery_policy or RecoveryPolicy.default_for(sdef.tool_id),
            )
            if target == "system.processes" and "limit" in intent.parameters:
                step.params["limit"] = intent.parameters["limit"]
            elif target in {"app.discovery", "executor.launch"}:
                step.params.update(intent.parameters)
            if target == "executor.launch":
                app_name = str(intent.parameters.get("app_name", "")).strip()
                evidence = Planner._application_evidence(context, app_name, app_profiles)
                if evidence:
                    confidence = float(evidence.get("confidence", 0.0))
                    step.description = (
                        f"Launch {app_name} (detected via {evidence.get('source', 'system')}, "
                        f"confidence {confidence:.0%}; execution still requires policy authorization)"
                    )
                elif app_name and app_name not in {"browser", "default-browser", "navegador"}:
                    step.description = f"Launch {app_name} (not confirmed by the current application catalog)"
            steps.append(step)
            self._emit(event_types.PLANNER_STEP_CREATED, session_id=sid, request_id=rid, details={"step_id": step.id, "tool_id": step.tool_id})

        risk_score = self._calculate_risk(steps, intent, context)
        total_est = sum(s.estimated_duration_ms or 500 for s in steps if s.estimated_duration_ms)

        if goal:
            risk_score = max(risk_score, self._goal_risk_score(goal))

        desc = f"{intent.action} {target} in {len(steps)} step(s)"
        if goal:
            desc = f"Goal: {goal.name} | {desc}"

        plan = Plan(
            steps=steps,
            intent=intent,
            risk_score=risk_score,
            estimated_duration_ms=total_est,
            description=desc,
            goal=goal,
        )
        self._emit(event_types.PLANNER_COMPLETED, session_id=sid, request_id=rid, status="completed", details={"step_count": len(plan.steps)})
        return plan

    def _application_evidence(
        context: Optional[Dict[str, Any]],
        app_name: str,
        app_profiles: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[Dict[str, Any]]:
        if not app_name:
            return None

        # Prefer explicit app_profiles if provided (from orchestrator)
        if app_profiles:
            query = app_name.casefold().removesuffix(".exe")
            for app in app_profiles:
                if not isinstance(app, dict):
                    continue
                name = str(app.get("name") or app.get("Name") or "").casefold().removesuffix(".exe")
                if name == query:
                    return app
            return None

        # Fallback to deep_context
        if not context:
            return None
        deep_context = context.get("deep_context", context)
        apps = deep_context.get("installed_apps", []) if isinstance(deep_context, dict) else []
        query = app_name.casefold().removesuffix(".exe")
        for app in apps if isinstance(apps, list) else []:
            if not isinstance(app, dict):
                continue
            name = str(app.get("name") or app.get("Name") or "").casefold().removesuffix(".exe")
            if name == query:
                return app
        return None

    def _calculate_risk(self, steps: List[PlanStep], intent: Intent, context: Optional[Dict[str, Any]] = None) -> float:
        impact_scores = {"low": 0.1, "medium": 0.4, "high": 0.7, "critical": 1.0}
        max_impact = 0.0
        for step in steps:
            score = impact_scores.get(step.estimated_impact, 0.3)
            if not step.is_reversible:
                score += 0.1
            max_impact = max(max_impact, score)

        action_risk = {"query": 0.0, "analyze": 0.1, "configure": 0.3, "execute": 0.6, "control": 0.4}
        action_score = action_risk.get(intent.action, 0.2)

        risk = max_impact * 0.6 + action_score * 0.4

        if context:
            deep_ctx = context.get("deep_context", {})
            if isinstance(deep_ctx, dict):
                hardware = deep_ctx.get("hardware", {})
                if isinstance(hardware, dict):
                    gpu_avail = hardware.get("gpu_available")
                    if intent.action == "execute" and gpu_avail is False:
                        for step in steps:
                            if any(kw in step.description.lower() for kw in ("gpu", "cuda", "render", "3d")):
                                risk += 0.15
                                break
                    vram = hardware.get("gpu_vram_gb")
                    if vram is not None and isinstance(vram, (int, float)) and vram < 4:
                        for step in steps:
                            if any(kw in step.description.lower() for kw in ("llm", "ai", "model", "training")):
                                risk += 0.1
                                break
                installed_apps = deep_ctx.get("installed_apps", [])
                if isinstance(installed_apps, list) and intent.action == "execute":
                    for step in steps:
                        app_name = step.params.get("app") or step.params.get("name") or ""
                        if not app_name:
                            continue
                        evidence = Planner._application_evidence(context, app_name, installed_apps)
                        if evidence is None:
                            risk += 0.08
                            break

        return min(risk, 1.0)

    def resolve_dependencies(self, plan: Plan) -> List[List[PlanStep]]:
        ids = [step.id for step in plan.steps]
        if len(ids) != len(set(ids)):
            logger.error("Duplicate step id detected in plan %s", plan.description)
            return []
        step_map = {s.id: s for s in plan.steps}
        invalid_dependency = False
        for s in plan.steps:
            for dep in s.depends_on:
                if dep not in step_map:
                    logger.error("Step '%s' depends on unknown step '%s'", s.id, dep)
                    invalid_dependency = True
        if invalid_dependency:
            return []

        in_degree: Dict[str, int] = {s.id: 0 for s in plan.steps}
        adj: Dict[str, List[str]] = {s.id: [] for s in plan.steps}

        for s in plan.steps:
            for dep in s.depends_on:
                if dep in step_map:
                    adj.setdefault(dep, []).append(s.id)
                    in_degree[s.id] = in_degree.get(s.id, 0) + 1

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        levels: List[List[str]] = []

        while queue:
            next_queue = []
            for sid in queue:
                for neighbor in adj.get(sid, []):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_queue.append(neighbor)
            levels.append(queue)
            queue = next_queue

        if sum(len(level) for level in levels) != len(plan.steps):
            logger.error("Circular dependency detected in plan %s", plan.description)
            return []

        return [[step_map[sid] for sid in level] for level in levels]

    def describe_plan(self, plan: Plan) -> str:
        lines = [f"Plan: {plan.description}"]
        lines.append(f"Risk: {plan.risk_score:.2f} | Steps: {len(plan.steps)}")
        levels = self.resolve_dependencies(plan)
        for i, level in enumerate(levels):
            for step in level:
                rev = " [reversible]" if step.is_reversible else " [irreversible]"
                dep = f" after {step.depends_on}" if step.depends_on else ""
                parallel = " [parallel]" if len(level) > 1 else ""
                lines.append(f"  {i + 1}.{step.id}. {step.tool_id}: {step.description}{rev}{dep}{parallel}")
        return "\n".join(lines)
