"""Opt-in control for passive Executor Sandbox V2."""

from pydantic import BaseModel, ConfigDict

EXECUTOR_SANDBOX_V2_ENABLED = False


class ExecutorSandboxControl(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = EXECUTOR_SANDBOX_V2_ENABLED
    authority: bool = False
    execution_requested: bool = False
