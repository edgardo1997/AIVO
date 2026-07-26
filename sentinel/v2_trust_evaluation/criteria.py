"""Validated scoring criteria over aggregate historical evidence."""

from pydantic import BaseModel, ConfigDict, Field


class TrustCriteriaV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_windows_for_review: int = Field(default=3, ge=1, le=1000)
    minimum_integrity_rate: float = Field(default=0.99, ge=0, le=1)
    maximum_error_rate: float = Field(default=0.01, ge=0, le=1)
    maximum_critical_divergences: int = Field(default=0, ge=0)
    trust_ready_score: float = Field(default=85, ge=0, le=100)
