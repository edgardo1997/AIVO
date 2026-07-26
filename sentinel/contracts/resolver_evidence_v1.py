"""Evidence emitted by a future ApplicationResolver."""

from datetime import datetime
from enum import Enum
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


class ResolverVerificationStateV1(str, Enum):
    DISCOVERED = "DISCOVERED"
    VERIFIED = "VERIFIED"
    INVALIDATED = "INVALIDATED"


AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]


class ResolverEvidenceV1(BaseModel):
    """Immutable resolver provenance prepared for future verification."""

    model_config = FROZEN_MODEL_CONFIG

    schema_version: Literal["1.0"]
    resolver_id: NonEmptyString
    resolver_version: NonEmptyString
    resolver_identity: NonEmptyString
    source_type: NonEmptyString
    source_reference: NonEmptyString
    discovered_at: AwareDatetime
    metadata_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    confidence: float = Field(ge=0.0, le=1.0)
    verification_state: ResolverVerificationStateV1
    verification_method: str | None = None
    verified_at: AwareDatetime | None = None

    @property
    def verified(self) -> bool:
        return self.verification_state is ResolverVerificationStateV1.VERIFIED

    @model_validator(mode="after")
    def validate_verification_state(self) -> "ResolverEvidenceV1":
        if self.verification_state is ResolverVerificationStateV1.DISCOVERED:
            if self.verified_at is not None:
                raise ValueError("DISCOVERED evidence cannot have verified_at")
        elif self.verification_state is ResolverVerificationStateV1.VERIFIED:
            if not self.verification_method or not self.verification_method.strip():
                raise ValueError("VERIFIED evidence requires verification_method")
            if self.verified_at is None:
                raise ValueError("VERIFIED evidence requires verified_at")
            if self.verified_at < self.discovered_at:
                raise ValueError("verified_at cannot be earlier than discovered_at")
        elif self.verification_state is ResolverVerificationStateV1.INVALIDATED:
            if not self.verification_method or not self.verification_method.strip():
                raise ValueError("INVALIDATED evidence requires verification_method")
        return self
