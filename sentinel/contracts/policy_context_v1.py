"""Complete, immutable authorization context for future policy evaluation."""

import hashlib
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    model_validator,
)

from ._base import (
    FROZEN_MODEL_CONFIG,
    NonEmptyString,
    require_timezone,
)
from .execution_plan_v2 import FrozenDict


class PolicyContextV1(BaseModel):
    """Identity, plan, risk, and versioned policy provenance."""

    model_config = FROZEN_MODEL_CONFIG

    schema_version: Literal["1.0"]
    user_id: NonEmptyString
    identity_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    plan_id: NonEmptyString
    intent_id: NonEmptyString
    risk_level: NonEmptyString
    evaluated_policies: tuple[NonEmptyString, ...] = Field(min_length=1)
    evaluated_policy_versions: dict[str, NonEmptyString]
    evaluated_at: Annotated[datetime, AfterValidator(require_timezone)]
    policy_engine_version: NonEmptyString
    decision_origin: NonEmptyString

    @staticmethod
    def calculate_identity_hash(user_id: str) -> str:
        return hashlib.sha256(user_id.encode("utf-8")).hexdigest()

    @model_validator(mode="after")
    def validate_binding(self) -> "PolicyContextV1":
        expected_identity = self.calculate_identity_hash(self.user_id)
        if self.identity_hash != expected_identity:
            raise ValueError("identity_hash does not match user_id")
        if set(self.evaluated_policy_versions) != set(self.evaluated_policies):
            raise ValueError("evaluated_policy_versions must contain exactly every evaluated policy")
        object.__setattr__(
            self,
            "evaluated_policy_versions",
            FrozenDict(self.evaluated_policy_versions),
        )
        return self
