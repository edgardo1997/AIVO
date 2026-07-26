from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Any, Dict, List, Optional

from .intent import Intent
from .planner import Plan
from .simulation import SimulationResult

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConsentType(str, Enum):
    ONCE = "once"
    SESSION = "session"
    PERMANENT = "permanent"


@dataclass
class RiskClassification:
    level: RiskLevel
    score: float
    label: str
    description: str
    is_read_only: bool
    is_reversible: bool
    affected_resources: List[str] = field(default_factory=list)
    estimated_impact: str = ""
    simulation_summary: str = ""
    context_factors: List[str] = field(default_factory=list)
    irreversible: bool = False


RISK_DESCRIPTIONS = {
    RiskLevel.LOW: {
        "label": "Bajo",
        "description": "Acción segura: solo lectura o abrir una aplicación conocida.",
    },
    RiskLevel.MEDIUM: {
        "label": "Medio",
        "description": "Modificaciones reversibles o abrir una aplicación no verificada.",
    },
    RiskLevel.HIGH: {
        "label": "Alto",
        "description": "Cambios significativos en el sistema. Requiere verificación.",
    },
    RiskLevel.CRITICAL: {
        "label": "Crítico",
        "description": "Operación irreversible. Puede causar pérdida de datos o daño al sistema.",
    },
}


KNOWN_APP_TOOLS = {"executor.launch", "executor.command"}

LOW_READ_TOOLS = {
    "system.health",
    "system.info",
    "system.cpu",
    "system.memory",
    "system.disk",
    "system.network",
    "system.processes",
    "system.gpu",
    "filesystem.read",
    "filesystem.search",
    "filesystem.list",
    "app.discovery",
}

MEDIUM_REVERSIBLE_TOOLS = {
    "filesystem.write",
    "executor.kill",
    "executor.restart",
}

HIGH_SYSTEM_TOOLS = {
    "filesystem.delete",
}

CRITICAL_TOOLS = set()

SUSPICIOUS_PATH_MARKERS = (
    "\\temp\\",
    "\\tmp\\",
    "\\appdata\\local\\temp\\",
    "\\downloads\\",
    "\\users\\public\\",
)

KNOWN_APP_NAMES = frozenset(
    {
        "notepad",
        "calc",
        "calculator",
        "chrome",
        "edge",
        "firefox",
        "brave",
        "opera",
        "word",
        "excel",
        "paint",
        "powershell",
        "terminal",
        "cmd",
        "explorer",
        "taskmgr",
        "code",
        "vscode",
        "winword",
        "excel",
        "outlook",
        "powerpnt",
        "msaccess",
    }
)


class RiskClassifier:
    def __init__(self, objective_assessor=None, simulation_engine=None, knowledge_service=None):
        self._assessor = objective_assessor
        self._simulation = simulation_engine
        self._knowledge = knowledge_service

    def set_objective_assessor(self, assessor) -> None:
        self._assessor = assessor

    def set_simulation_engine(self, engine) -> None:
        self._simulation = engine

    def set_knowledge_service(self, svc) -> None:
        self._knowledge = svc

    def classify(
        self,
        intent: Intent,
        plan: Plan,
        context: Optional[Dict[str, Any]] = None,
        simulation_result: Optional[SimulationResult] = None,
    ) -> RiskClassification:
        context = context or {}

        target_tool = intent.target or ""
        is_read_only = self._is_read_only_intent(intent, plan)
        level = self._classify_level(target_tool, intent, plan, context)
        score = self._level_to_score(level)

        sim = simulation_result
        if sim is None and self._simulation is not None:
            try:
                sim = self._simulation.simulate(plan, context)
            except Exception:
                sim = None

        has_irreversible = False
        if sim:
            has_irreversible = any(getattr(i, "irreversible", False) for i in getattr(sim, "impacts", []))
            if has_irreversible and level != RiskLevel.CRITICAL:
                level = RiskLevel.HIGH
                score = self._level_to_score(level)

        desc = RISK_DESCRIPTIONS.get(level, RISK_DESCRIPTIONS[RiskLevel.LOW])
        description = self._build_description(level, target_tool, intent, context)
        label = desc["label"]

        affected = self._extract_resources(plan, sim)
        impact = self._estimate_impact(plan, intent, sim)

        return RiskClassification(
            level=level,
            score=score,
            label=label,
            description=description,
            is_read_only=is_read_only,
            is_reversible=not has_irreversible,
            affected_resources=affected,
            estimated_impact=impact,
            simulation_summary=getattr(sim, "summary", "") if sim else "",
            irreversible=has_irreversible,
        )

    def _classify_level(self, target_tool: str, intent: Intent, plan: Plan, context: Dict[str, Any]) -> RiskLevel:
        # CRITICAL: explicitly destructive tools
        if target_tool in CRITICAL_TOOLS:
            return RiskLevel.CRITICAL

        # HIGH: system-modifying tools
        if target_tool in HIGH_SYSTEM_TOOLS:
            return RiskLevel.HIGH

        # MEDIUM: reversible modifications
        if target_tool in MEDIUM_REVERSIBLE_TOOLS:
            return RiskLevel.MEDIUM

        # LOW: read-only operations
        if target_tool in LOW_READ_TOOLS:
            return RiskLevel.LOW

        if target_tool == "executor.command":
            return RiskLevel.MEDIUM

        # executor.launch: classify by whether the app is known
        if target_tool == "executor.launch":
            return self._classify_launch(intent, context)

        # Fallback: check the plan
        return self._classify_by_plan(plan)

    def _classify_launch(self, intent: Intent, context: Dict[str, Any]) -> RiskLevel:
        app_name = str(intent.parameters.get("app_name", "")).strip().lower()
        if not app_name:
            return RiskLevel.MEDIUM

        is_store_app = "!" in app_name
        if is_store_app:
            return RiskLevel.LOW

        known_apps = context.get("known_apps", [])
        if known_apps and any(a.lower() == app_name for a in known_apps):
            return RiskLevel.LOW

        if self._knowledge is not None:
            try:
                if app_name in self._knowledge.known_apps():
                    return RiskLevel.LOW
                profile = self._knowledge.lookup(app_name)
                if profile and profile.confidence >= 0.7:
                    return RiskLevel.LOW
            except Exception:
                logger.debug("Application knowledge lookup failed", exc_info=True)

        # HIGH: suspicious paths (temp, downloads, public)
        executable_path = str(intent.parameters.get("executable_path", "") or intent.parameters.get("path", "")).lower()
        if executable_path and any(marker in executable_path for marker in SUSPICIOUS_PATH_MARKERS):
            return RiskLevel.HIGH

        # HIGH: names that contain known app names as substrings (possible impersonation)
        base_name = app_name.removesuffix(".exe")
        if base_name != app_name and base_name in KNOWN_APP_NAMES:
            return RiskLevel.LOW
        for known in KNOWN_APP_NAMES:
            if known in base_name and known != base_name:
                return RiskLevel.HIGH

        return RiskLevel.MEDIUM

    def _classify_by_plan(self, plan: Plan) -> RiskLevel:
        impacts = [getattr(s, "estimated_impact", "medium") for s in plan.steps]
        if "critical" in impacts:
            return RiskLevel.CRITICAL
        if "high" in impacts:
            return RiskLevel.HIGH
        if "medium" in impacts:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _is_read_only_intent(self, intent: Intent, plan: Plan) -> bool:
        if intent.action == "query":
            return True
        if intent.action in ("analyze", "execute") and intent.target in LOW_READ_TOOLS:
            return True
        if all(getattr(step, "estimated_impact", "medium") in ("low", "none") for step in plan.steps):
            return True
        return False

    def _level_to_score(self, level: RiskLevel) -> float:
        return {
            RiskLevel.LOW: 0.1,
            RiskLevel.MEDIUM: 0.4,
            RiskLevel.HIGH: 0.7,
            RiskLevel.CRITICAL: 0.95,
        }.get(level, 0.1)

    def _build_description(self, level: RiskLevel, target_tool: str, intent: Intent, context: Dict[str, Any]) -> str:
        if level == RiskLevel.LOW and target_tool == "executor.launch":
            return "Abrir una aplicación conocida. No se modifica el sistema."
        if level == RiskLevel.LOW:
            return "Solo lectura. No se modifica el sistema."
        if level == RiskLevel.MEDIUM and target_tool == "executor.launch":
            return "Abrir una aplicación no verificada. Se requiere confirmación."
        if level == RiskLevel.MEDIUM:
            return "Acción reversible. No hay riesgo de pérdida de datos."
        if level == RiskLevel.HIGH:
            return "Cambios significativos en el sistema. Se recomienda verificar antes de continuar."
        if level == RiskLevel.CRITICAL:
            return "Operación irreversible. Puede causar pérdida de datos o daño al sistema."
        return RISK_DESCRIPTIONS.get(level, RISK_DESCRIPTIONS[RiskLevel.LOW])["description"]

    def _estimate_impact(self, plan: Plan, intent: Intent, sim: Optional[SimulationResult]) -> str:
        if sim and getattr(sim, "summary", ""):
            return sim.summary
        target = intent.target or ""
        if target == "executor.launch":
            app = intent.parameters.get("app_name", "")
            return f"Voy a iniciar {app}." if app else "Voy a iniciar una aplicación."
        if target == "executor.command":
            return "Voy a ejecutar un comando en el sistema."
        if target in LOW_READ_TOOLS:
            return "Solo lectura del sistema. No se realizan cambios."
        if target == "filesystem.write":
            return "Voy a modificar un archivo."
        if target == "filesystem.delete":
            return "Voy a eliminar un archivo. Esta acción puede ser irreversible."
        parts = []
        for step in plan.steps:
            tool = getattr(step, "tool_id", "")
            impact = getattr(step, "estimated_impact", "medium")
            parts.append(f"{tool} ({impact})")
        return "; ".join(parts) if parts else "Voy a ejecutar la acción solicitada."

    def _extract_resources(self, plan: Plan, sim: Optional[SimulationResult]) -> List[str]:
        resources = []
        for step in plan.steps:
            tool = getattr(step, "tool_id", "")
            params = getattr(step, "params", {})
            if "target" in params:
                resources.append(f"{tool}: {params['target']}")
            elif "path" in params:
                resources.append(str(params["path"]))
            elif "process" in params:
                resources.append(str(params["process"]))
            elif tool:
                resources.append(tool)
        if sim:
            for impact in getattr(sim, "impacts", []):
                desc = getattr(impact, "description", "")
                if desc and desc not in resources:
                    resources.append(desc)
        return resources
