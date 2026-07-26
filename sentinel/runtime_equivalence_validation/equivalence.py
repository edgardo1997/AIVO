"""Immutable sanitized runtime snapshots and classifications."""

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
CodeValue = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")]


class EquivalenceClassification(str, Enum):
    EQUIVALENT = "EQUIVALENT"
    FUNCTIONAL_DIFFERENCE = "FUNCTIONAL_DIFFERENCE"
    SECURITY_DIFFERENCE = "SECURITY_DIFFERENCE"
    TIMING_DIFFERENCE = "TIMING_DIFFERENCE"
    UNEXPECTED_RESULT = "UNEXPECTED_RESULT"
    UNKNOWN = "UNKNOWN"


class RuntimeEquivalenceSnapshotV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    runtime_type: Literal["LEGACY", "V2"]
    intent_hash: HashValue
    execution_plan_hash: HashValue
    discovery_hash: HashValue
    policy_hash: HashValue
    authorization_hash: HashValue
    runtime_status: CodeValue
    execution_result: CodeValue
    tool_selection_hash: HashValue
    event_sequence: tuple[CodeValue, ...]
    execution_timing_ms: float = Field(ge=0)
    return_code: CodeValue
