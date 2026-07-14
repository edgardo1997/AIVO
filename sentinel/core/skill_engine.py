import json
import time
from typing import Any, Dict, List, Optional
import logging

from .skill import SkillRegistry, SkillSpec, SkillResult
from .tool_gateway import ToolGateway
from .model_router import ModelRouter, TaskType
from .planner import Plan, PlanStep, Intent

logger = logging.getLogger(__name__)


class SkillEngine:
    def __init__(
        self,
        registry: SkillRegistry,
        tool_gateway: Optional[ToolGateway] = None,
        model_router: Optional[ModelRouter] = None,
    ):
        self._registry = registry
        self._tool_gateway = tool_gateway
        self._model_router = model_router

    @property
    def registry(self) -> SkillRegistry:
        return self._registry

    def _validate_params(self, skill: SkillSpec, params: Dict[str, Any]) -> Optional[str]:
        schema = skill.input_schema
        if not schema:
            return None
        required = schema.get("required", [])
        for field in required:
            if field not in params or params[field] is None or params[field] == "":
                return f"Missing required parameter: '{field}'"
        props = schema.get("properties", {})
        for key, value in params.items():
            if key in props:
                prop = props[key]
                prop_type = prop.get("type")
                if prop_type == "string" and not isinstance(value, str):
                    return f"Parameter '{key}' must be a string"
                if prop_type == "integer" and not isinstance(value, int):
                    return f"Parameter '{key}' must be an integer"
                if prop_type == "boolean" and not isinstance(value, bool):
                    return f"Parameter '{key}' must be a boolean"
                if "enum" in prop and value not in prop["enum"]:
                    return f"Parameter '{key}' must be one of {prop['enum']}"
        return None

    def find_skills(self, task: str) -> List[Dict[str, Any]]:
        skills = self._registry.find_for_task(task)
        return [s.to_dict() for s in skills]

    async def execute(
        self,
        skill_id: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        start = time.time()
        context = context or {}

        skill = self._registry.get(skill_id)
        if not skill:
            return SkillResult(
                skill_id=skill_id, success=False,
                error=f"Skill '{skill_id}' not found",
            )

        validation_error = self._validate_params(skill, params)
        if validation_error:
            return SkillResult(
                skill_id=skill_id, success=False,
                error=validation_error,
            )

        plan = await self._build_plan(skill, params, context)
        if not plan or not plan.steps:
            return SkillResult(
                skill_id=skill_id, success=False,
                error="Failed to build execution plan from skill",
                plan_summary=skill.description,
            )

        tool_results = []
        overall_success = True
        last_data = None

        for step in plan.steps:
            if not self._tool_gateway:
                tool_results.append({
                    "step_id": step.id,
                    "success": False,
                    "error": "ToolGateway not available",
                })
                overall_success = False
                continue

            step_context = dict(context)
            step_context["skill_id"] = skill_id
            step_context["skill_name"] = skill.name

            result = await self._tool_gateway.execute(step.tool_id, step.params, step_context)
            step_entry = {
                "step_id": step.id,
                "tool_id": step.tool_id,
                "success": result.success,
                "error": result.error,
                "data": result.data,
                "duration_ms": result.duration_ms,
            }
            tool_results.append(step_entry)

            if result.success:
                last_data = result.data
            else:
                overall_success = False
                break

        duration = (time.time() - start) * 1000

        return SkillResult(
            skill_id=skill_id,
            success=overall_success,
            data=last_data,
            plan_summary=plan.description or skill.description,
            duration_ms=duration,
            tool_results=tool_results,
        )

    async def _build_plan(
        self,
        skill: SkillSpec,
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Optional[Plan]:
        if not self._tool_gateway:
            return Plan(
                steps=[], intent=Intent(action="execute", target=skill.id, parameters=params),
                description=skill.description,
            )

        steps: List[PlanStep] = []
        for idx, tool_id in enumerate(skill.tools):
            spec = self._tool_gateway.get_spec(tool_id)
            step_params = dict(params)
            step = PlanStep(
                id=f"{skill.id.replace('.', '_')}_{idx}",
                tool_id=tool_id,
                params=step_params,
                description=f"{skill.name} step {idx + 1}: {tool_id}",
            )
            steps.append(step)

        return Plan(
            steps=steps,
            intent=Intent(action="execute", target=skill.id, parameters=params),
            description=f"Skill: {skill.name} ({skill.id})",
        )

    async def suggest(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        skills = self.find_skills(task)
        if not skills:
            return {"matched": False, "skills": [], "message": "No matching skills found"}
        return {
            "matched": True,
            "skills": skills,
            "message": f"Found {len(skills)} matching skill(s) for '{task}'",
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skills": self._registry.to_dict(),
            "total_skills": len(self._registry.list()),
        }
