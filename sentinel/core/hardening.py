from __future__ import annotations

import asyncio
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from sentinel.core.circuit_breaker import CircuitBreaker
from sentinel.core.recovery import (
    ErrorCategory, ErrorClassifier, RecoveryPolicy, RetryExhaustedError,
)
from sentinel.core.tool import ToolResult

logger = logging.getLogger(__name__)


@dataclass
class HardeningConfig:
    default_timeout_seconds: int = 30
    default_circuit_breaker_threshold: int = 3
    default_circuit_breaker_cooldown: float = 30.0
    default_retry_jitter: float = 0.1
    tool_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def get_timeout(self, tool_id: str) -> int:
        override = self.tool_overrides.get(tool_id, {})
        return override.get("timeout_seconds", self.default_timeout_seconds)

    def get_circuit_breaker_threshold(self, tool_id: str) -> int:
        override = self.tool_overrides.get(tool_id, {})
        return override.get("circuit_breaker_threshold", self.default_circuit_breaker_threshold)

    def get_circuit_breaker_cooldown(self, tool_id: str) -> float:
        override = self.tool_overrides.get(tool_id, {})
        return override.get("circuit_breaker_cooldown", self.default_circuit_breaker_cooldown)

    def get_retry_jitter(self, tool_id: str) -> float:
        override = self.tool_overrides.get(tool_id, {})
        return override.get("retry_jitter", self.default_retry_jitter)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "default_timeout_seconds": self.default_timeout_seconds,
            "default_circuit_breaker_threshold": self.default_circuit_breaker_threshold,
            "default_circuit_breaker_cooldown": self.default_circuit_breaker_cooldown,
            "default_retry_jitter": self.default_retry_jitter,
            "tool_overrides": dict(self.tool_overrides),
        }


class ToolCircuitBreaker:
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 30.0):
        self._cb = CircuitBreaker(
            failure_threshold=failure_threshold,
            cooldown_seconds=cooldown_seconds,
        )

    def allow_request(self, tool_id: str) -> bool:
        return self._cb.allow_request(tool_id)

    def record_success(self, tool_id: str) -> None:
        self._cb.record_success(tool_id)

    def record_failure(self, tool_id: str) -> None:
        self._cb.record_failure(tool_id)

    def get_state(self, tool_id: str) -> Dict[str, Any]:
        return self._cb.get_state(tool_id)

    def get_all_states(self) -> List[Dict[str, Any]]:
        return self._cb.get_all_states()

    def reset(self, tool_id: Optional[str] = None) -> int:
        return self._cb.reset(tool_id)


class EnhancedRetryHandler:
    def __init__(self, classifier: Optional[ErrorClassifier] = None):
        self._classifier = classifier or ErrorClassifier()

    async def execute(
        self,
        execute_fn: Callable[[], Any],
        policy: RecoveryPolicy,
        tool_id: str = "",
        jitter: float = 0.1,
    ) -> Any:
        last_error: Optional[str] = None
        for attempt in range(1, policy.max_retries + 1):
            try:
                result = await execute_fn()
                if getattr(result, "success", True):
                    return result
                last_error = getattr(result, "error", None) or "unknown error"
                category = self._classifier.classify(last_error, tool_id)
                if category != ErrorCategory.TRANSIENT or "transient" not in policy.retry_on:
                    return result
                logger.info("Retry %d/%d for %s after transient error: %s",
                            attempt, policy.max_retries, tool_id, last_error)
            except Exception as e:
                last_error = str(e)
                category = self._classifier.classify(last_error, tool_id)
                if category != ErrorCategory.TRANSIENT or "transient" not in policy.retry_on:
                    raise
                logger.info("Retry %d/%d for %s after transient exception: %s",
                            attempt, policy.max_retries, tool_id, last_error)
            if attempt < policy.max_retries:
                delay = min(
                    policy.retry_delay_ms * (policy.retry_backoff ** (attempt - 1)),
                    policy.retry_max_delay_ms,
                ) / 1000
                if jitter > 0:
                    delay += random.uniform(0, delay * jitter)
                await asyncio.sleep(delay)
        raise RetryExhaustedError(tool_id, policy.max_retries, last_error)


class TimeoutManager:
    def __init__(self, config: HardeningConfig):
        self._config = config

    async def execute(
        self,
        execute_fn: Callable[[], Any],
        tool_id: str,
        spec_timeout: Optional[int] = None,
    ) -> Any:
        timeout = spec_timeout or self._config.get_timeout(tool_id)
        try:
            return await asyncio.wait_for(execute_fn(), timeout=timeout)
        except asyncio.TimeoutError:
            elapsed = timeout * 1000
            return ToolResult.fail(
                error=f"Tool '{tool_id}' timed out after {timeout}s",
                tool_id=tool_id,
                duration_ms=elapsed,
            )


class HealthChecker:
    def __init__(self, circuit_breaker: ToolCircuitBreaker):
        self._cb = circuit_breaker

    def check_tool_health(self, tool_id: str) -> Dict[str, Any]:
        state = self._cb.get_state(tool_id) if tool_id else {"state": "closed"}
        return {
            "tool_id": tool_id,
            "healthy": state.get("state") != "open",
            "circuit_state": state.get("state", "closed"),
            "consecutive_failures": state.get("consecutive_failures", 0),
        }

    def check_system_health(self) -> Dict[str, Any]:
        import os
        import psutil
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage(os.path.abspath(".")).percent,
        }


class HardeningService:
    def __init__(self, config: Optional[HardeningConfig] = None):
        self._config = config or HardeningConfig()
        self._circuit_breaker = ToolCircuitBreaker(
            failure_threshold=self._config.default_circuit_breaker_threshold,
            cooldown_seconds=self._config.default_circuit_breaker_cooldown,
        )
        self._timeout_manager = TimeoutManager(self._config)
        self._retry_handler = EnhancedRetryHandler()
        self._health_checker = HealthChecker(self._circuit_breaker)
        self._lock = threading.RLock()
        self._stats: Dict[str, Any] = {
            "timeouts": 0,
            "circuit_breaker_blocks": 0,
            "retries_attempted": 0,
            "retries_successful": 0,
            "failures_by_category": {category.value: 0 for category in ErrorCategory},
        }

    @property
    def config(self) -> HardeningConfig:
        return self._config

    @property
    def circuit_breaker(self) -> ToolCircuitBreaker:
        return self._circuit_breaker

    @property
    def timeout_manager(self) -> TimeoutManager:
        return self._timeout_manager

    @property
    def retry_handler(self) -> EnhancedRetryHandler:
        return self._retry_handler

    @property
    def health_checker(self) -> HealthChecker:
        return self._health_checker

    def update_config(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)

    def set_tool_override(self, tool_id: str, **overrides) -> None:
        with self._lock:
            if tool_id not in self._config.tool_overrides:
                self._config.tool_overrides[tool_id] = {}
            self._config.tool_overrides[tool_id].update(overrides)

    def get_tool_override(self, tool_id: str) -> Dict[str, Any]:
        return dict(self._config.tool_overrides.get(tool_id, {}))

    def remove_tool_override(self, tool_id: str) -> bool:
        with self._lock:
            return self._config.tool_overrides.pop(tool_id, None) is not None

    def record_timeout(self) -> None:
        with self._lock:
            self._stats["timeouts"] += 1

    def record_circuit_block(self) -> None:
        with self._lock:
            self._stats["circuit_breaker_blocks"] += 1

    def record_retry(self, success: bool) -> None:
        with self._lock:
            self._stats["retries_attempted"] += 1
            if success:
                self._stats["retries_successful"] += 1

    def classify_failure(self, error: str, tool_id: str = "") -> ErrorCategory:
        category = ErrorClassifier.classify(error, tool_id)
        with self._lock:
            self._stats["failures_by_category"][category.value] += 1
        return category

    @staticmethod
    def should_trip_circuit(category: ErrorCategory) -> bool:
        # Policy decisions and bad input are not dependency-health failures.
        return category in (ErrorCategory.TRANSIENT, ErrorCategory.FATAL)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            result = dict(self._stats)
        result["config"] = self._config.to_dict()
        result["circuit_breaker_states"] = self._circuit_breaker.get_all_states()
        return result

    def check_health(self) -> Dict[str, Any]:
        return {
            "system": self._health_checker.check_system_health(),
            "tools": {
                s["provider_id"]: {"healthy": s["state"] != "open", **s}
                for s in self._circuit_breaker.get_all_states()
            },
            "stats": {
                k: v for k, v in self._stats.items()
            },
        }
