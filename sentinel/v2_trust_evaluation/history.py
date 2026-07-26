"""Immutable aggregate-only historical evidence."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HistoricalEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    window_count: int = Field(ge=0)
    total_events: int = Field(ge=0)
    stable_windows: int = Field(ge=0)
    equivalence_rate: float = Field(ge=0, le=1)
    integrity_rate: float = Field(ge=0, le=1)
    healthy_window_rate: float = Field(ge=0, le=1)
    error_rate: float = Field(ge=0, le=1)
    divergence_rate: float = Field(ge=0, le=1)
    critical_divergences: int = Field(ge=0)
    incident_count: int = Field(ge=0)
    rollback_count: int = Field(ge=0)

    @property
    def stability_rate(self) -> float:
        return self.stable_windows / max(self.window_count, 1)

    @model_validator(mode="after")
    def validate_window_counts(self) -> "HistoricalEvidenceV1":
        if self.stable_windows > self.window_count:
            raise ValueError("stable windows cannot exceed total windows")
        return self


class HistorySummary:
    """Read-only aggregation boundary; it never mutates evidence sources."""

    def summarize(
        self,
        evidence: HistoricalEvidenceV1,
    ) -> HistoricalEvidenceV1:
        return evidence.model_copy(deep=True)
