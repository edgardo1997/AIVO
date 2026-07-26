"""Opt-in parallel runtime canary with no execution authority."""

from .control import RUNTIME_CANARY_ENABLED, runtime_canary_enabled
from .diagnostics import RuntimeCanaryInput, RuntimeCanaryResult
from .dispatcher import RuntimeCanaryDispatcher
from .metrics import RuntimeCanaryMetrics, RuntimeCanaryMetricsSnapshot
from .pipeline import RuntimeCanaryPipeline

__all__ = [
    "RUNTIME_CANARY_ENABLED",
    "RuntimeCanaryDispatcher",
    "RuntimeCanaryInput",
    "RuntimeCanaryMetrics",
    "RuntimeCanaryMetricsSnapshot",
    "RuntimeCanaryPipeline",
    "RuntimeCanaryResult",
    "runtime_canary_enabled",
]
