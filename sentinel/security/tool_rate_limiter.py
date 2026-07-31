"""Tool rate limiter — controls call frequency per tool.

Controls:
  - Call count per time window
  - Frequency per tool
  - Sensitive tool limits
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List, Optional, Tuple

from sentinel.security.models import RiskLevel

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    max_calls: int
    window_seconds: int

    def __post_init__(self) -> None:
        if self.max_calls < 1:
            raise ValueError("max_calls must be >= 1")
        if self.window_seconds < 1:
            raise ValueError("window_seconds must be >= 1")


@dataclass
class RateLimitResult:
    allowed: bool
    current_count: int
    max_calls: int
    window_seconds: int
    retry_after: Optional[float] = None
    reason: str = ""

    @property
    def blocked(self) -> bool:
        return not self.allowed


DEFAULT_RATE_LIMITS: Dict[str, RateLimitConfig] = {
    # Chat / conversation
    "chat.respond": RateLimitConfig(max_calls=60, window_seconds=60),
    "conversation.*": RateLimitConfig(max_calls=120, window_seconds=60),
    # Filesystem — sensitive
    "filesystem.read": RateLimitConfig(max_calls=60, window_seconds=60),
    "filesystem.write": RateLimitConfig(max_calls=10, window_seconds=60),
    "filesystem.delete": RateLimitConfig(max_calls=3, window_seconds=60),
    "filesystem.copy": RateLimitConfig(max_calls=10, window_seconds=60),
    "filesystem.move": RateLimitConfig(max_calls=10, window_seconds=60),
    "filesystem.create": RateLimitConfig(max_calls=20, window_seconds=60),
    "filesystem.search": RateLimitConfig(max_calls=30, window_seconds=60),
    "filesystem.format": RateLimitConfig(max_calls=1, window_seconds=3600),
    # Process / execution
    "executor.command": RateLimitConfig(max_calls=10, window_seconds=60),
    "executor.launch": RateLimitConfig(max_calls=15, window_seconds=60),
    "executor.kill": RateLimitConfig(max_calls=5, window_seconds=60),
    "process.*": RateLimitConfig(max_calls=20, window_seconds=60),
    # Browser / network
    "browser.open": RateLimitConfig(max_calls=30, window_seconds=60),
    "browser.*": RateLimitConfig(max_calls=60, window_seconds=60),
    "network.*": RateLimitConfig(max_calls=30, window_seconds=60),
    "web.*": RateLimitConfig(max_calls=30, window_seconds=60),
    # System
    "system.shutdown": RateLimitConfig(max_calls=1, window_seconds=3600),
    "system.reboot": RateLimitConfig(max_calls=1, window_seconds=3600),
    # Identity / permissions
    "identity.*": RateLimitConfig(max_calls=10, window_seconds=60),
    "permission.*": RateLimitConfig(max_calls=10, window_seconds=60),
    # AI / models
    "ai.*": RateLimitConfig(max_calls=30, window_seconds=60),
    "model.*": RateLimitConfig(max_calls=30, window_seconds=60),
    # Default for unlisted tools
    "*": RateLimitConfig(max_calls=60, window_seconds=60),
}


class ToolRateLimiter:
    """Sliding-window rate limiter per tool.

    Thread-safe. Uses per-tool sliding windows with second granularity.
    """

    def __init__(self, limits: Optional[Dict[str, RateLimitConfig]] = None):
        self._limits: Dict[str, RateLimitConfig] = dict(DEFAULT_RATE_LIMITS)
        if limits:
            self._limits.update(limits)
        self._windows: Dict[str, List[float]] = defaultdict(list)
        self._lock = Lock()

    def set_limit(self, tool_name: str, config: RateLimitConfig) -> None:
        with self._lock:
            self._limits[tool_name] = config

    def get_limit(self, tool_name: str) -> RateLimitConfig:
        config = self._limits.get(tool_name)
        if config:
            return config
        for pattern, cfg in self._limits.items():
            if pattern.endswith("*") and tool_name.startswith(pattern[:-1]):
                return cfg
        return self._limits.get("*", RateLimitConfig(max_calls=60, window_seconds=60))

    def check(self, tool_name: str) -> RateLimitResult:
        config = self.get_limit(tool_name)
        now = time.monotonic()
        window_start = now - config.window_seconds

        with self._lock:
            window = self._windows[tool_name]
            window[:] = [t for t in window if t > window_start]
            current_count = len(window)

            if current_count >= config.max_calls:
                oldest = window[0] if window else now
                retry_after = max(0.0, oldest + config.window_seconds - now)
                return RateLimitResult(
                    allowed=False,
                    current_count=current_count,
                    max_calls=config.max_calls,
                    window_seconds=config.window_seconds,
                    retry_after=retry_after,
                    reason=f"Rate limit exceeded for '{tool_name}': {current_count}/{config.max_calls} per {config.window_seconds}s",
                )

            window.append(now)
            return RateLimitResult(
                allowed=True,
                current_count=current_count + 1,
                max_calls=config.max_calls,
                window_seconds=config.window_seconds,
            )

    def reset(self, tool_name: Optional[str] = None) -> None:
        with self._lock:
            if tool_name:
                self._windows.pop(tool_name, None)
            else:
                self._windows.clear()

    def get_stats(self) -> Dict[str, Dict[str, int]]:
        with self._lock:
            now = time.monotonic()
            result = {}
            for tool_name, timestamps in self._windows.items():
                config = self.get_limit(tool_name)
                active = sum(1 for t in timestamps if t > now - config.window_seconds)
                result[tool_name] = {
                    "active_in_window": active,
                    "limit": config.max_calls,
                    "window_seconds": config.window_seconds,
                }
            return result
