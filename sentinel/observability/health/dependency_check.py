"""Dependency health checks for infrastructure components."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import logging
import time

from sentinel.observability.health.health_checker import ComponentHealth, HealthState

logger = logging.getLogger(__name__)


@dataclass
class DependencyResult:
    database: ComponentHealth
    memory: ComponentHealth
    model_router: ComponentHealth
    tool_gateway: ComponentHealth
    event_bus: Optional[ComponentHealth] = None
    storage: Optional[ComponentHealth] = None
    extras: Dict[str, ComponentHealth] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "database": self.database.to_dict(),
            "memory": self.memory.to_dict(),
            "model_router": self.model_router.to_dict(),
            "tool_gateway": self.tool_gateway.to_dict(),
        }
        if self.event_bus:
            result["event_bus"] = self.event_bus.to_dict()
        if self.storage:
            result["storage"] = self.storage.to_dict()
        for k, v in self.extras.items():
            result[k] = v.to_dict()
        return result

    @property
    def all_healthy(self) -> bool:
        return all(
            c.state == HealthState.HEALTHY
            for c in [self.database, self.memory, self.model_router, self.tool_gateway]
            + ([self.event_bus] if self.event_bus else [])
            + ([self.storage] if self.storage else [])
            + list(self.extras.values())
        )


class DependencyChecker:
    def __init__(self):
        self._providers: Dict[str, Callable[[], ComponentHealth]] = {}

    def register(self, name: str, check_fn: Callable[[], ComponentHealth]) -> None:
        self._providers[name] = check_fn

    def check_database(self) -> ComponentHealth:
        fn = self._providers.get("database")
        if fn:
            return fn()
        return ComponentHealth(name="database", state=HealthState.HEALTHY, details={"message": "No database configured"})

    def check_memory(self) -> ComponentHealth:
        fn = self._providers.get("memory")
        if fn:
            return fn()
        return ComponentHealth(name="memory", state=HealthState.HEALTHY, details={"message": "No memory checker configured"})

    def check_model_router(self) -> ComponentHealth:
        fn = self._providers.get("model_router")
        if fn:
            return fn()
        return ComponentHealth(name="model_router", state=HealthState.HEALTHY, details={"message": "No router checker configured"})

    def check_tool_gateway(self) -> ComponentHealth:
        fn = self._providers.get("tool_gateway")
        if fn:
            return fn()
        return ComponentHealth(name="tool_gateway", state=HealthState.HEALTHY, details={"message": "No gateway checker configured"})

    def check_event_bus(self) -> Optional[ComponentHealth]:
        fn = self._providers.get("event_bus")
        if fn:
            return fn()
        return None

    def check_storage(self) -> Optional[ComponentHealth]:
        fn = self._providers.get("storage")
        if fn:
            return fn()
        return None

    def check_all(self) -> DependencyResult:
        return DependencyResult(
            database=self.check_database(),
            memory=self.check_memory(),
            model_router=self.check_model_router(),
            tool_gateway=self.check_tool_gateway(),
            event_bus=self.check_event_bus(),
            storage=self.check_storage(),
        )
