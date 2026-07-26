import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

log = logging.getLogger("sentinel.provider_health")


class HealthState(Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    DISABLED = "disabled"


@dataclass
class HealthResult:
    provider_id: str
    state: HealthState
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    checked_at: float = field(default_factory=time.time)
    is_local: bool = False

    def to_dict(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "state": self.state.value,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "checked_at": self.checked_at,
            "is_local": self.is_local,
        }


class ProviderHealthChecker:
    """Periodically checks provider health and internet connectivity.

    Caches results with a configurable TTL to avoid hammering endpoints.
    """

    def __init__(
        self,
        network_monitor=None,
        check_interval: float = 30.0,
        probe_timeout: float = 5.0,
        availability_ttl: float = 15.0,
    ):
        self._network_monitor = network_monitor
        self._interval = check_interval
        self._timeout = probe_timeout
        self._ttl = availability_ttl
        self._cache: Dict[str, HealthResult] = {}
        self._internet_online: Optional[bool] = None
        self._internet_last_checked: float = 0.0
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def set_network_monitor(self, monitor) -> None:
        self._network_monitor = monitor

    @property
    def internet_online(self) -> bool:
        if self._network_monitor is not None and self._network_monitor.is_initialized:
            return self._network_monitor.is_online
        if self._internet_online is not None:
            return self._internet_online
        return True

    def _check_internet_sync(self) -> bool:
        """Quick synchronous internet check via dns or socket."""
        import socket

        for host in ("8.8.8.8", "1.1.1.1", "google.com"):
            try:
                socket.setdefaulttimeout(self._timeout)
                socket.gethostbyname(host)
                self._internet_online = True
                self._internet_last_checked = time.time()
                return True
            except OSError:
                continue
        self._internet_online = False
        self._internet_last_checked = time.time()
        return False

    def check_health(self, provider_id: str, base_url: str) -> HealthResult:
        """Synchronous health check for a single provider via HTTP GET."""
        now = time.time()
        cached = self._cache.get(provider_id)
        if cached and now - cached.checked_at < self._ttl:
            return cached

        import httpx

        start = time.perf_counter()
        try:
            resp = httpx.get(f"{base_url.rstrip('/')}/models", timeout=self._timeout)
            latency = (time.perf_counter() - start) * 1000
            if resp.is_success:
                result = HealthResult(
                    provider_id=provider_id,
                    state=HealthState.AVAILABLE,
                    latency_ms=round(latency, 1),
                    checked_at=now,
                )
            elif resp.status_code >= 500:
                result = HealthResult(
                    provider_id=provider_id,
                    state=HealthState.DEGRADED,
                    latency_ms=round(latency, 1),
                    error=f"HTTP {resp.status_code}",
                    checked_at=now,
                )
            else:
                result = HealthResult(
                    provider_id=provider_id,
                    state=HealthState.DEGRADED,
                    error=f"HTTP {resp.status_code}",
                    checked_at=now,
                )
        except httpx.TimeoutException:
            result = HealthResult(
                provider_id=provider_id,
                state=HealthState.OFFLINE,
                error="timeout",
                checked_at=now,
            )
        except httpx.ConnectError:
            result = HealthResult(
                provider_id=provider_id,
                state=HealthState.OFFLINE,
                error="connection_refused",
                checked_at=now,
            )
        except Exception as exc:
            result = HealthResult(
                provider_id=provider_id,
                state=HealthState.OFFLINE,
                error=str(exc)[:200],
                checked_at=now,
            )
        self._cache[provider_id] = result
        return result

    def is_provider_available(self, provider_id: str, spec) -> bool:
        """Return True if a provider can be used right now."""
        if spec and spec.is_local:
            return True
        if not self.internet_online:
            return False
        if spec and spec.requires_key:
            return True
        health = self._cache.get(provider_id)
        if health and time.time() - health.checked_at < self._ttl:
            return health.state in (HealthState.AVAILABLE, HealthState.DEGRADED)
        return True

    def get_provider_state(self, provider_id: str) -> HealthState:
        cached = self._cache.get(provider_id)
        if cached:
            return cached.state
        return HealthState.AVAILABLE

    def clear_cache(self) -> None:
        self._cache.clear()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._task = asyncio.create_task(self._run())
        except RuntimeError:
            pass

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        while self._running:
            await asyncio.sleep(self._interval)
            if self._network_monitor:
                self._internet_online = self._network_monitor.is_online
