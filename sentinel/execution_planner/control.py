"""Opt-in control for passive Execution Planner V2."""

from pydantic import BaseModel, ConfigDict

EXECUTION_PLANNER_V2_ENABLED = False


class ExecutionPlannerControl(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = EXECUTION_PLANNER_V2_ENABLED
    authority: bool = False
    execution_requested: bool = False
