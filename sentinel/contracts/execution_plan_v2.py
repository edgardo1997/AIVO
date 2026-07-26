"""Versioned, tamper-evident execution planning contracts.

ExecutionPlanV2 captures immutable step parameters and verifies a canonical
SHA-256 hash. It does not replace the current Planner or Plan dataclasses.
"""

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, model_validator

from ._base import FROZEN_MODEL_CONFIG, NonEmptyString


class FrozenDict(dict):
    """Recursively immutable JSON-object representation."""

    def __init__(self, values: Mapping[str, Any] | None = None):
        frozen = {key: _freeze_json(value) for key, value in (values or {}).items()}
        dict.__init__(self, frozen)

    def _immutable(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("versioned contract parameters are immutable")

    __delitem__ = _immutable
    __ior__ = _immutable
    __setitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable

    def __deepcopy__(self, memo: dict[int, Any]) -> "FrozenDict":
        return self


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return FrozenDict(value)
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_json(item) for item in value)
    return value


class ExecutionStepV2(BaseModel):
    """One immutable, versioned tool invocation within an execution plan."""

    model_config = FROZEN_MODEL_CONFIG

    schema_version: Literal["2.0"]
    step_id: NonEmptyString
    tool_id: NonEmptyString
    parameters: dict[str, Any]
    depends_on: tuple[str, ...] = ()
    description: str = ""
    estimated_duration_ms: float | None = Field(default=None, ge=0.0)
    model_decision: dict[str, Any] | None = None
    estimated_impact: Literal[
        "low",
        "medium",
        "high",
        "critical",
    ] = "low"
    is_reversible: bool = Field(
        default=False,
        validation_alias=AliasChoices("is_reversible", "reversible"),
    )
    rollback_tool_id: str | None = None
    rollback_params: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices(
            "rollback_params",
            "rollback_parameters",
        ),
    )
    recovery_policy: dict[str, Any] | None = None

    @model_validator(mode="after")
    def freeze_parameters(self) -> "ExecutionStepV2":
        object.__setattr__(self, "parameters", FrozenDict(self.parameters))
        object.__setattr__(
            self,
            "rollback_params",
            FrozenDict(self.rollback_params),
        )
        if self.recovery_policy is not None:
            object.__setattr__(
                self,
                "recovery_policy",
                FrozenDict(self.recovery_policy),
            )
        return self

    @property
    def reversible(self) -> bool:
        """Compatibility accessor for the previous field name."""
        return self.is_reversible

    @property
    def rollback_parameters(self) -> dict[str, Any]:
        """Compatibility accessor for the previous field name."""
        return self.rollback_params


class ExecutionPlanV2(BaseModel):
    """Immutable execution plan whose canonical contents are hash-verified."""

    model_config = FROZEN_MODEL_CONFIG

    schema_version: Literal["2.0"]
    plan_id: NonEmptyString
    intent_id: NonEmptyString
    steps: tuple[ExecutionStepV2, ...]
    params_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    description: str = ""
    goal: dict[str, Any] | None = None
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    estimated_duration_ms: float | None = Field(default=None, ge=0.0)

    @staticmethod
    def calculate_params_hash(
        *,
        intent_id: str,
        steps: tuple[ExecutionStepV2, ...] | list[ExecutionStepV2],
    ) -> str:
        payload = {
            "intent_id": intent_id,
            "steps": [step.model_dump(mode="json") for step in steps],
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @model_validator(mode="after")
    def verify_params_hash(self) -> "ExecutionPlanV2":
        expected = self.calculate_params_hash(
            intent_id=self.intent_id,
            steps=self.steps,
        )
        if self.params_hash != expected:
            raise ValueError("params_hash does not match canonical plan contents")
        return self
