"""Failure-isolated equivalence validator."""

import time
import uuid
from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict

from sentinel.contracts import DecisionResultV1
from sentinel.contracts._base import require_timezone

from .comparator import EquivalenceComparison, RuntimeSnapshotComparator
from .control import RuntimeEquivalenceControl
from .equivalence import (
    EquivalenceClassification,
    RuntimeEquivalenceSnapshotV1,
)
from .metrics import EquivalenceMetrics


class EquivalenceResultMetricsV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    compared_fields: int
    matching_fields: int
    timing_delta_ms: float


class RuntimeEquivalenceResultV1(DecisionResultV1):
    result_id: str
    timestamp: Annotated[datetime, AfterValidator(require_timezone)]
    classification: EquivalenceClassification
    differences: tuple[str, ...]
    metrics: EquivalenceResultMetricsV1


class RuntimeEquivalenceValidator:
    def __init__(
        self,
        *,
        control: RuntimeEquivalenceControl,
        metrics: EquivalenceMetrics | None = None,
        comparator: RuntimeSnapshotComparator | None = None,
    ) -> None:
        self.control = control
        self.metrics = metrics or EquivalenceMetrics()
        self.comparator = comparator or RuntimeSnapshotComparator()

    def validate(
        self,
        legacy: RuntimeEquivalenceSnapshotV1,
        v2: RuntimeEquivalenceSnapshotV1,
    ) -> RuntimeEquivalenceResultV1 | None:
        if not self.control.enabled:
            return None
        started = time.perf_counter()
        error = False
        try:
            comparison = self.comparator.compare(legacy, v2)
        except Exception:
            error = True
            comparison = EquivalenceComparison(
                classification=EquivalenceClassification.UNKNOWN,
                differences=("COMPARISON_ERROR",),
                compared_fields=0,
                matching_fields=0,
                timing_delta_ms=0,
            )
        latency = (time.perf_counter() - started) * 1000
        self.metrics.record(
            classification=comparison.classification,
            latency_ms=latency,
            error=error,
        )
        return RuntimeEquivalenceResultV1(
            result_id=f"equivalence_{uuid.uuid4().hex}",
            timestamp=datetime.now(timezone.utc),
            classification=comparison.classification,
            differences=comparison.differences,
            metrics=EquivalenceResultMetricsV1(
                compared_fields=comparison.compared_fields,
                matching_fields=comparison.matching_fields,
                timing_delta_ms=comparison.timing_delta_ms,
            ),
        )
