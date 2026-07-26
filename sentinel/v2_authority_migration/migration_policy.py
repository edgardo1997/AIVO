"""Immutable constraints for a limited authority trial."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MigrationPolicyV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed_operations: tuple[str, ...]
    traffic_percentage: float = Field(gt=0, le=10)
    fallback_conditions: tuple[str, ...]
    maximum_trial_seconds: int = Field(gt=0, le=86400)
    rollback_criteria: tuple[str, ...]

    @field_validator(
        "allowed_operations",
        "fallback_conditions",
        "rollback_criteria",
    )
    @classmethod
    def validate_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("migration policy lists cannot be empty")
        for value in values:
            if not value or len(value) > 64 or not value.replace("_", "").replace(".", "").isalnum():
                raise ValueError("migration policy values must be sanitized")
        return values
