"""Isolated canary session with bounded aggregate observation."""

import hashlib
import re
from dataclasses import dataclass, field

from .metrics import CanaryEnvironmentMetrics


@dataclass
class CanarySessionV1:
    session_id: str
    correlation_id: str
    memory_limit_mb: float
    timeout_seconds: float
    metrics: CanaryEnvironmentMetrics = field(
        default_factory=CanaryEnvironmentMetrics,
        repr=False,
    )

    @classmethod
    def create(
        cls,
        *,
        environment_id: str,
        correlation_id: str,
        memory_limit_mb: float = 128.0,
        timeout_seconds: float = 3600.0,
    ) -> "CanarySessionV1":
        if memory_limit_mb <= 0 or timeout_seconds <= 0:
            raise ValueError("session limits must be positive")
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", correlation_id):
            raise ValueError("correlation_id must be sanitized")
        digest = hashlib.sha256(f"{environment_id}|{correlation_id}".encode("utf-8")).hexdigest()[:24]
        return cls(
            session_id=f"session_{digest}",
            correlation_id=correlation_id,
            memory_limit_mb=float(memory_limit_mb),
            timeout_seconds=float(timeout_seconds),
        )

    def within_memory_limit(self, memory_mb: float) -> bool:
        return 0 <= memory_mb <= self.memory_limit_mb
