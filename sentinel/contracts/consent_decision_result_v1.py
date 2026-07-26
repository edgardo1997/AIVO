"""Immutable human-consent record without execution authority."""

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, Field, model_validator

from ._base import require_timezone
from .decision import DecisionResultV1
from .simulation_result_v1 import SimulationActionTypeV1

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]
HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]


class ConsentDecisionValueV1(str, Enum):
    CONSENT_PENDING = "CONSENT_PENDING"
    CONSENT_GRANTED = "CONSENT_GRANTED"
    CONSENT_DENIED = "CONSENT_DENIED"
    CONSENT_EXPIRED = "CONSENT_EXPIRED"
    CONSENT_REVOKED = "CONSENT_REVOKED"


class ConsentDecisionResultV1(DecisionResultV1):
    """Evidence-bound consent fact; granting does not authorize execution."""

    consent_id: SafeIdentifier
    correlation_id: SafeIdentifier
    evidence_hash: HashValue
    issuer_id: SafeIdentifier
    timestamp: AwareDatetime
    request_type: SimulationActionTypeV1
    decision: ConsentDecisionValueV1
    decision_source: SafeIdentifier
    expiration_time: AwareDatetime
    revoked: bool
    confidence: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_decision_semantics(self) -> "ConsentDecisionResultV1":
        human_decisions = {
            ConsentDecisionValueV1.CONSENT_GRANTED,
            ConsentDecisionValueV1.CONSENT_DENIED,
            ConsentDecisionValueV1.CONSENT_REVOKED,
        }
        if self.decision in human_decisions and not self.decision_source.startswith("human:"):
            raise ValueError("human consent decisions require a human source")
        if self.decision is ConsentDecisionValueV1.CONSENT_REVOKED:
            if not self.revoked:
                raise ValueError("revoked consent must set revoked=true")
        elif self.revoked:
            raise ValueError("only revoked consent may set revoked=true")
        if self.decision is ConsentDecisionValueV1.CONSENT_EXPIRED:
            if self.expiration_time > self.timestamp:
                raise ValueError("expired consent must be past expiration")
        elif self.expiration_time <= self.timestamp:
            raise ValueError("consent expiration must follow its timestamp")
        return self
