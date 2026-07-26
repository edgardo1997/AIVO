"""Safe configurable thresholds for long-run validation."""

from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class ThresholdManager:
    observation_window: timedelta = timedelta(hours=72)
    memory_limit_mb: float = 256.0
    warning_memory_ratio: float = 0.5
    error_rate_limit: float = 0.01
    critical_consecutive_errors: int = 10
    max_dropped_event_rate: float = 0.01
    max_latency_ms: float = 250.0

    def __post_init__(self) -> None:
        if self.observation_window <= timedelta(0):
            raise ValueError("observation_window must be positive")
        if self.memory_limit_mb <= 0 or self.max_latency_ms <= 0:
            raise ValueError("memory and latency limits must be positive")
        if not 0 < self.warning_memory_ratio < 1:
            raise ValueError("warning_memory_ratio must be between 0 and 1")
        if not 0 <= self.error_rate_limit <= 1:
            raise ValueError("error_rate_limit must be between 0 and 1")
        if not 0 <= self.max_dropped_event_rate <= 1:
            raise ValueError("max_dropped_event_rate must be between 0 and 1")
        if self.critical_consecutive_errors < 1:
            raise ValueError("critical_consecutive_errors must be positive")
