"""Health System — component health checks and system status evaluation."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import logging
import time

logger = logging.getLogger(__name__)


class HealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    RECOVERING = "recovering"
    FAILED = "failed"


@dataclass
class ComponentHealth:
    name: str
    state: HealthState
    latency_ms: float = 0.0
    error: Optional[str] = None
    last_check: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "latency_ms": round(self.latency_ms, 1),
            "error": self.error,
            "last_check": self.last_check,
            "details": self.details,
        }


@dataclass
class HealthStatus:
    state: HealthState
    components: Dict[str, ComponentHealth] = field(default_factory=dict)
    uptime_seconds: float = 0.0
    version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.state.value,
            "version": self.version,
            "uptime": self._format_uptime(),
            "components": {k: v.to_dict() for k, v in self.components.items()},
        }

    def _format_uptime(self) -> str:
        secs = int(self.uptime_seconds)
        hours = secs // 3600
        mins = (secs % 3600) // 60
        secs = secs % 60
        return f"{hours}h{mins}m{secs}s"


HealthCheckFn = Callable[[], ComponentHealth]


class HealthChecker:
    def __init__(self, version: str = "1.0"):
        self._checks: Dict[str, HealthCheckFn] = {}
        self._start_time: float = time.monotonic()
        self._version: str = version

    def register(self, name: str, check_fn: HealthCheckFn) -> None:
        self._checks[name] = check_fn

    def unregister(self, name: str) -> None:
        self._checks.pop(name, None)

    def check(self, name: str) -> ComponentHealth:
        fn = self._checks.get(name)
        if fn is None:
            return ComponentHealth(name=name, state=HealthState.FAILED, error=f"No check registered for '{name}'")
        try:
            return fn()
        except Exception as e:
            logger.warning("Health check '%s' failed: %s", name, e)
            return ComponentHealth(name=name, state=HealthState.FAILED, error=str(e)[:200])

    def check_all(self) -> HealthStatus:
        components: Dict[str, ComponentHealth] = {}
        worst = HealthState.HEALTHY
        for name in self._checks:
            ch = self.check(name)
            components[name] = ch
            if self._worse(ch.state, worst):
                worst = ch.state
        return HealthStatus(
            state=worst,
            components=components,
            uptime_seconds=time.monotonic() - self._start_time,
            version=self._version,
        )

    def check_subset(self, names: List[str]) -> HealthStatus:
        components: Dict[str, ComponentHealth] = {}
        worst = HealthState.HEALTHY
        for name in names:
            fn = self._checks.get(name)
            if fn is None:
                ch = ComponentHealth(name=name, state=HealthState.FAILED, error="Unknown component")
            else:
                try:
                    ch = fn()
                except Exception as e:
                    ch = ComponentHealth(name=name, state=HealthState.FAILED, error=str(e)[:200])
            components[name] = ch
            if self._worse(ch.state, worst):
                worst = ch.state
        return HealthStatus(state=worst, components=components, uptime_seconds=time.monotonic() - self._start_time, version=self._version)

    @staticmethod
    def _worse(a: HealthState, b: HealthState) -> bool:
        order = {HealthState.HEALTHY: 0, HealthState.RECOVERING: 1, HealthState.DEGRADED: 2, HealthState.FAILED: 3}
        return order.get(a, 0) > order.get(b, 0)

    @property
    def uptime(self) -> float:
        return time.monotonic() - self._start_time

    @property
    def registered_components(self) -> List[str]:
        return list(self._checks.keys())
