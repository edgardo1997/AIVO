import logging
import time
from typing import Any, Dict, Optional
from sentinel.core.model_router import ProviderSpec, ProviderAvailability

logger = logging.getLogger(__name__)


class HealthChecker:
    def __init__(self):
        self._internet_online: Optional[bool] = None
        self._last_check: float = 0.0
        self._check_interval: float = 30.0

    @property
    def internet_online(self) -> bool:
        if self._internet_online is not None and time.monotonic() - self._last_check < self._check_interval:
            return self._internet_online
        self._internet_online = self._check_internet()
        self._last_check = time.monotonic()
        return self._internet_online

    @staticmethod
    def _check_internet() -> bool:
        try:
            import httpx
            r = httpx.get("https://www.google.com", timeout=2.0)
            return r.status_code == 200
        except Exception:
            return False

    async def check_provider_health(self, provider_id: str, timeout: float = 5.0) -> Dict[str, Any]:
        import httpx
        from sentinel.core.model_router import PROVIDER_URLS
        url = PROVIDER_URLS.get(provider_id)
        if not url:
            return {"provider": provider_id, "available": False, "error": "unknown_provider"}
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.get(url.rstrip("/v1") if "/v1" in url else url)
                return {"provider": provider_id, "available": r.status_code < 500, "status_code": r.status_code}
        except Exception as e:
            return {"provider": provider_id, "available": False, "error": str(e)[:100]}
