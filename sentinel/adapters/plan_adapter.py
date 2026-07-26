"""Pure adapter from legacy Plan/PlanStep models to ExecutionPlanV2."""

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from sentinel.contracts import ExecutionPlanV2, ExecutionStepV2
from sentinel.core.planner import Plan

from ._ids import generated_id, require_id


def _json_metadata(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "to_dict"):
        return deepcopy(value.to_dict())
    if is_dataclass(value):
        return _json_metadata(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_metadata(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_metadata(item) for item in value]
    return deepcopy(value)


def plan_to_v2(
    plan: Plan,
    *,
    intent_id: str,
    plan_id: str | None = None,
) -> ExecutionPlanV2:
    """Convert a legacy plan and calculate its canonical parameter hash.

    ``intent_id`` is explicit because the legacy Plan embeds an Intent that has
    no stable identifier.
    """
    if not isinstance(plan, Plan):
        raise TypeError("plan must be a sentinel.core.planner.Plan")

    resolved_intent_id = require_id(intent_id, "intent_id")
    steps = tuple(
        ExecutionStepV2(
            schema_version="2.0",
            step_id=step.id,
            tool_id=step.tool_id,
            parameters=deepcopy(step.params),
            depends_on=tuple(step.depends_on),
            description=step.description,
            estimated_duration_ms=step.estimated_duration_ms,
            model_decision=_json_metadata(step.model_decision),
            estimated_impact=step.estimated_impact,
            is_reversible=step.is_reversible,
            rollback_tool_id=step.rollback_tool_id,
            rollback_params=deepcopy(step.rollback_params or {}),
            recovery_policy=_json_metadata(step.recovery_policy),
        )
        for step in plan.steps
    )
    params_hash = ExecutionPlanV2.calculate_params_hash(
        intent_id=resolved_intent_id,
        steps=steps,
    )
    return ExecutionPlanV2(
        schema_version="2.0",
        plan_id=plan_id or generated_id("plan"),
        intent_id=resolved_intent_id,
        steps=steps,
        params_hash=params_hash,
        description=plan.description,
        goal=_json_metadata(plan.goal),
        risk_score=plan.risk_score,
        estimated_duration_ms=plan.estimated_duration_ms,
    )
