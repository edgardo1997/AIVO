"""Non-authoritative engine comparing complete decision snapshots."""

import time
import uuid
from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator

from sentinel.contracts import DecisionResultV1
from sentinel.contracts._base import require_timezone

from .classification import DecisionClassification
from .comparison import (
    ComponentComparison,
    ComponentComparisonStatus,
    DecisionComparison,
)
from .control import DecisionShadowValidationControl
from .decision_capture import LegacyDecisionSnapshot, V2DecisionSnapshot
from .metrics import DecisionShadowMetrics


class DecisionShadowResultV1(DecisionResultV1):
    validation_id: str
    timestamp: Annotated[datetime, AfterValidator(require_timezone)]
    legacy_hash: str
    v2_hash: str
    component_comparison: ComponentComparison
    classification: DecisionClassification
    error_codes: tuple[str, ...] = ()


class DecisionShadowValidationEngine:
    def __init__(
        self,
        *,
        control: DecisionShadowValidationControl,
        metrics: DecisionShadowMetrics | None = None,
        comparator: type[DecisionComparison] = DecisionComparison,
    ) -> None:
        self.control = control
        self.metrics = metrics or DecisionShadowMetrics()
        self._comparator = comparator

    def validate(
        self,
        legacy: LegacyDecisionSnapshot,
        v2: V2DecisionSnapshot,
    ) -> DecisionShadowResultV1 | None:
        if not self.control.enabled:
            return None
        started = time.perf_counter()
        error = False
        try:
            components, classification = self._comparator.compare(legacy, v2)
            error_codes: tuple[str, ...] = ()
        except Exception:
            error = True
            components = ComponentComparison(
                intent=ComponentComparisonStatus.DIFFERENT,
                plan=ComponentComparisonStatus.DIFFERENT,
                policy=ComponentComparisonStatus.DIFFERENT,
                discovery=ComponentComparisonStatus.DIFFERENT,
                authorization=ComponentComparisonStatus.DIFFERENT,
            )
            classification = DecisionClassification.CRITICAL_DIVERGENCE
            error_codes = ("COMPARISON_ERROR",)
        latency = (time.perf_counter() - started) * 1000
        self.metrics.record(
            classification=classification,
            latency_ms=latency,
            error=error,
        )
        return DecisionShadowResultV1(
            validation_id=f"validation_{uuid.uuid4().hex}",
            timestamp=datetime.now(timezone.utc),
            legacy_hash=legacy.canonical_hash(),
            v2_hash=v2.canonical_hash(),
            component_comparison=components,
            classification=classification,
            error_codes=error_codes,
        )
