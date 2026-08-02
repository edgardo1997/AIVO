"""Alert Engine — detects anomalies and triggers notifications."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import logging
import time

logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    name: str
    level: AlertLevel
    message: str
    timestamp: str = ""
    component: str = ""
    value: Optional[float] = None
    threshold: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "level": self.level.value,
            "message": self.message,
            "timestamp": self.timestamp,
            "component": self.component,
            "value": self.value,
            "threshold": self.threshold,
            "metadata": self.metadata,
        }


@dataclass
class AlertRule:
    name: str
    description: str
    check_fn: Callable[[], Optional[Alert]]
    interval_seconds: float = 60.0
    cooldown_seconds: float = 300.0
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "description": self.description, "interval_seconds": self.interval_seconds, "enabled": self.enabled}


class AlertEngine:
    """Monitors system conditions and raises alerts when thresholds are exceeded."""

    def __init__(self, alert_callback: Optional[Callable[[Alert], None]] = None):
        self._rules: List[AlertRule] = []
        self._alerts: List[Alert] = []
        self._last_fired: Dict[str, float] = {}
        self._callback = alert_callback
        self._max_alerts = 500

    def add_rule(self, rule: AlertRule) -> None:
        self._rules.append(rule)

    def add_custom_rule(self, name: str, description: str, check_fn: Callable[[], Optional[Alert]], interval_seconds: float = 60.0, cooldown_seconds: float = 300.0) -> None:
        self._rules.append(AlertRule(name=name, description=description, check_fn=check_fn, interval_seconds=interval_seconds, cooldown_seconds=cooldown_seconds))

    def check(self) -> List[Alert]:
        now = time.monotonic()
        fired: List[Alert] = []
        for rule in self._rules:
            if not rule.enabled:
                continue
            last = self._last_fired.get(rule.name, 0)
            if now - last < rule.interval_seconds:
                continue
            try:
                alert = rule.check_fn()
                if alert is not None:
                    if now - self._last_fired.get(rule.name, 0) >= rule.cooldown_seconds:
                        self._last_fired[rule.name] = now
                        self._alerts.append(alert)
                        fired.append(alert)
                        if self._callback:
                            try:
                                self._callback(alert)
                            except Exception:
                                logger.warning("Alert callback failed", exc_info=True)
                        if len(self._alerts) > self._max_alerts:
                            self._alerts = self._alerts[-self._max_alerts:]
            except Exception as e:
                logger.debug("Alert rule '%s' check failed: %s", rule.name, e)
        return fired

    def check_all(self) -> List[Alert]:
        return self.check()

    def recent_alerts(self, limit: int = 50, level: Optional[AlertLevel] = None) -> List[Alert]:
        filtered = [a for a in self._alerts if level is None or a.level == level]
        return filtered[-limit:]

    def clear(self) -> None:
        self._alerts.clear()
        self._last_fired.clear()

    def summary(self) -> Dict[str, Any]:
        levels = {}
        for a in self._alerts:
            lv = a.level.value
            levels[lv] = levels.get(lv, 0) + 1
        return {
            "total_alerts": len(self._alerts),
            "by_level": levels,
            "active_rules": len(self._rules),
            "recent": [a.to_dict() for a in self._alerts[-5:]],
        }
