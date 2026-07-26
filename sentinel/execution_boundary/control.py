"""Opt-in control for passive Execution Boundary V2."""

from pydantic import BaseModel, ConfigDict

EXECUTION_BOUNDARY_V2_ENABLED = False


class ExecutionBoundaryControl(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = EXECUTION_BOUNDARY_V2_ENABLED
    authority: bool = False
    execution_requested: bool = False
