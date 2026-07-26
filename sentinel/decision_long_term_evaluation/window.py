"""Immutable evaluation window identity and lifecycle state."""

import hashlib
from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator

from sentinel.contracts import DecisionResultV1
from sentinel.contracts._base import require_timezone


class EvaluationWindowState(str, Enum):
    CREATED = "CREATED"
    COLLECTING = "COLLECTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EvaluationWindowV1(DecisionResultV1):
    evaluation_id: str
    started_at: Annotated[datetime, AfterValidator(require_timezone)]
    ended_at: Annotated[datetime, AfterValidator(require_timezone)] | None = None
    state: EvaluationWindowState = EvaluationWindowState.CREATED

    @classmethod
    def create(cls, started_at: datetime) -> "EvaluationWindowV1":
        digest = hashlib.sha256(started_at.isoformat().encode("utf-8")).hexdigest()
        return cls(
            evaluation_id=f"evaluation_{digest[:24]}",
            started_at=started_at,
        )

    @property
    def duration_seconds(self) -> float:
        if self.ended_at is None:
            return 0.0
        return max(0.0, (self.ended_at - self.started_at).total_seconds())
