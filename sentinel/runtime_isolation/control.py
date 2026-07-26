"""Opt-in control for passive Runtime Isolation V2."""

from pydantic import BaseModel, ConfigDict

RUNTIME_ISOLATION_V2_ENABLED = False


class RuntimeIsolationControl(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = RUNTIME_ISOLATION_V2_ENABLED
    authority: bool = False
    execution_requested: bool = False
