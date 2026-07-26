"""Opt-in shadow migration observability; not wired to runtime."""

from .decision_comparison import (
    ShadowDecisionComparison,
    ShadowDecisionComparisonStatus,
)
from .event_capture import CapturedRuntimeEvent, RuntimeEventCapture
from .metrics import ShadowDecisionMetrics
from .metrics_store import ShadowMetricsStore, ShadowMetricSnapshot
from .observer import (
    ShadowMigrationDiagnostic,
    ShadowMigrationGapType,
    ShadowMigrationMetrics,
    ShadowMigrationObserver,
    ShadowMigrationResult,
)
from .runtime_adapter import (
    RuntimeShadowAdapter,
    RuntimeShadowConversion,
    RuntimeShadowConversionStatus,
)
from .readiness import (
    CutoverReadinessReport,
    CutoverReadinessState,
    CutoverReadinessValidator,
)

__all__ = [
    "CutoverReadinessReport",
    "CutoverReadinessState",
    "CutoverReadinessValidator",
    "CapturedRuntimeEvent",
    "RuntimeShadowAdapter",
    "RuntimeShadowConversion",
    "RuntimeShadowConversionStatus",
    "ShadowDecisionComparison",
    "ShadowDecisionComparisonStatus",
    "ShadowDecisionMetrics",
    "ShadowMetricsStore",
    "ShadowMetricSnapshot",
    "RuntimeEventCapture",
    "ShadowMigrationDiagnostic",
    "ShadowMigrationGapType",
    "ShadowMigrationMetrics",
    "ShadowMigrationObserver",
    "ShadowMigrationResult",
]
