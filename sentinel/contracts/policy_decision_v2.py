"""Final policy-authority decision contract for the future migration.

PolicyDecisionV2 intentionally exposes only final policy outcomes. It is not a
DecisionEngine recommendation and is not wired into PolicyEngine yet.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Annotated, Literal

from pydantic import AfterValidator, BaseModel, model_validator

from ._base import (
    FROZEN_MODEL_CONFIG,
    NonEmptyString,
    require_timezone,
)
from .policy_context_v1 import PolicyContextV1


class PolicyDecisionValueV2(str, Enum):
    ALLOW = "ALLOW"
    REQUIRE_CONSENT = "REQUIRE_CONSENT"
    DENY = "DENY"


class PolicyDecisionV2(BaseModel):
    """Immutable final decision emitted by the future policy authority."""

    model_config = FROZEN_MODEL_CONFIG

    schema_version: Literal["2.0"]
    decision_id: NonEmptyString
    plan_id: NonEmptyString
    decision: PolicyDecisionValueV2
    policy_ids: tuple[NonEmptyString, ...]
    reason: NonEmptyString
    risk_context: dict[str, Any]
    timestamp: Annotated[datetime, AfterValidator(require_timezone)]
    policy_context: PolicyContextV1 | None = None

    @model_validator(mode="after")
    def validate_policy_context(self) -> "PolicyDecisionV2":
        if self.policy_context is None:
            return self
        if self.policy_context.plan_id != self.plan_id:
            raise ValueError("policy_context.plan_id must match decision plan_id")
        missing_versions = set(self.policy_ids) - set(self.policy_context.evaluated_policy_versions)
        if missing_versions:
            raise ValueError("policy_context is missing versions for decision policies")
        if self.policy_context.evaluated_at > self.timestamp:
            raise ValueError("policy context cannot be evaluated after the decision")
        return self


class PolicyDecisionV2Strict(PolicyDecisionV2):
    """Pre-cutover decision requiring complete policy and identity context."""

    policy_context: PolicyContextV1
    intent_id: NonEmptyString
    decision_origin: NonEmptyString

    @model_validator(mode="after")
    def validate_strict_binding(self) -> "PolicyDecisionV2Strict":
        if self.policy_context.intent_id != self.intent_id:
            raise ValueError("policy_context.intent_id must match decision intent_id")
        if self.policy_context.decision_origin != self.decision_origin:
            raise ValueError("policy_context.decision_origin must match decision_origin")
        return self
