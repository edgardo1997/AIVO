"""Network connectivity monitor for Sentinel.

Provides online/offline detection with callbacks and async wait support.
"""

import asyncio
import logging
import time
from typing import Callable, List, Optional

log = logging.getLogger("sentinel.network_monitor")

_DEFAULT_CHECK_URLS = [
    "https://httpbin.org/get",
    "https://google.com",
    "https://cloudflare.com",
]


class NetworkMonitor:
    """Monitors network connectivity by probing well-known endpoints.

    Fires callbacks on online→offline and offline→online transitions.
    """

    def __init__(
        self,
        check_urls: Optional[List[str]] = None,
        check_interval: float = 30.0,
        timeout: float = 5.0,
    ):
        self._check_urls = check_urls or list(_DEFAULT_CHECK_URLS)
        self._interval = check_interval
        self._timeout = timeout
        self._online: Optional[bool] = None
        self._last_check: float = 0.0
        self._callbacks: List[Callable[[bool], None]] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None

    @property
    def is_online(self) -> bool:
        return self._online if self._online is not None else False

    @property
    def is_initialized(self) -> bool:
        return self._online is not None

    def on_transition(self, callback: Callable[[bool], None]) -> None:
        """Register a callback fired on online/offline transitions."""
        self._callbacks.append(callback)

    async def check(self) -> bool:
        """Probe endpoints to determine connectivity."""
        import httpx

        for url in self._check_urls:
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    r = await client.get(url)
                    if r.is_success:
                        self._online = True
                        self._last_check = time.monotonic()
                        return True
            except Exception as exc:
                log.debug("Connectivity probe failed for %s: %s", url, exc)
                continue
        self._online = False
        self._last_check = time.monotonic()
        return False

    async def wait_online(self, timeout: float = 60.0) -> bool:
        """Wait until connectivity is restored. Returns True if online."""
        if self._online is True:
            return True
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if await self.check():
                return True
            await asyncio.sleep(2.0)
        return False

    async def start(self) -> None:
        """Start periodic background checks."""
        if self._running:
            return
        self._running = True
        prev = self._online
        await self.check()
        if prev is not None and prev != self._online:
            self._notify(self._online)
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self.close()

    def close(self) -> None:
        """Cancel background monitoring without requiring an active event loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        self._callbacks.clear()

    async def _run(self) -> None:
        while self._running:
            await asyncio.sleep(self._interval)
            prev = self._online
            await self.check()
            if prev is not None and prev != self._online:
                self._notify(self._online)

    def _notify(self, online: bool) -> None:
        state = "online" if online else "offline"
        log.info("Network transitioned to %s", state)
        for cb in self._callbacks:
            try:
                cb(online)
            except Exception as e:
                log.warning("Network transition callback failed: %s", e)
