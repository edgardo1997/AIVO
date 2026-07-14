from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import logging
import uuid

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


ALERT_SOURCES = [
    "cost", "performance", "circuit_breaker", "fallback",
    "network", "offline_queue", "system", "skill",
]


@dataclass
class Alert:
    id: str = ""
    alert_type: str = ""
    severity: AlertSeverity = AlertSeverity.INFO
    title: str = ""
    message: str = ""
    source: str = ""
    timestamp: str = ""
    acknowledged: bool = False
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "alert_type": self.alert_type,
            "severity": self.severity.value if isinstance(self.severity, AlertSeverity) else self.severity,
            "title": self.title,
            "message": self.message,
            "source": self.source,
            "timestamp": self.timestamp,
            "acknowledged": self.acknowledged,
            "data": dict(self.data),
        }


AlertHandler = Callable[[Alert], None]


class AlertManager:
    def __init__(self, max_alerts: int = 200):
        self._alerts: List[Alert] = []
        self._handlers: List[AlertHandler] = []
        self._max_alerts = max_alerts
        self._cost_tracker: Optional[Any] = None
        self._performance_tracker: Optional[Any] = None

    def set_cost_tracker(self, tracker: Any) -> None:
        self._cost_tracker = tracker

    def set_performance_tracker(self, tracker: Any) -> None:
        self._performance_tracker = tracker

    def register_handler(self, handler: AlertHandler) -> None:
        self._handlers.append(handler)

    def _make_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def emit(
        self,
        alert_type: str,
        severity: AlertSeverity,
        title: str,
        message: str,
        source: str = "",
        data: Optional[Dict[str, Any]] = None,
    ) -> Alert:
        alert = Alert(
            id=self._make_id(),
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            source=source or alert_type,
            timestamp=self._now(),
            data=data or {},
        )
        self._alerts.append(alert)
        if len(self._alerts) > self._max_alerts:
            self._alerts = self._alerts[-self._max_alerts:]

        logger.info("Alert [%s] %s: %s", severity.value, alert_type, title)
        for handler in self._handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.warning("Alert handler failed: %s", e)

        return alert

    def list(
        self,
        source: Optional[str] = None,
        severity: Optional[AlertSeverity] = None,
        acknowledged: Optional[bool] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        results = list(self._alerts)
        if source:
            results = [a for a in results if a.source == source]
        if severity:
            results = [a for a in results if a.severity == severity]
        if acknowledged is not None:
            results = [a for a in results if a.acknowledged == acknowledged]
        results.sort(key=lambda a: a.timestamp, reverse=True)
        return [a.to_dict() for a in results[:limit]]

    def acknowledge(self, alert_id: str) -> bool:
        for a in self._alerts:
            if a.id == alert_id:
                a.acknowledged = True
                return True
        return False

    def acknowledge_all(self, source: Optional[str] = None) -> int:
        count = 0
        for a in self._alerts:
            if source is None or a.source == source:
                if not a.acknowledged:
                    a.acknowledged = True
                    count += 1
        return count

    def clear(self, acknowledged_only: bool = True) -> int:
        if acknowledged_only:
            before = len(self._alerts)
            self._alerts = [a for a in self._alerts if not a.acknowledged]
            return before - len(self._alerts)
        count = len(self._alerts)
        self._alerts.clear()
        return count

    def check_all(self) -> int:
        count = 0
        if self._cost_tracker:
            try:
                budget_alerts = self._cost_tracker.check_budgets()
                for ba in budget_alerts:
                    self.emit(
                        alert_type="budget_exceeded",
                        severity=AlertSeverity.WARNING,
                        title=f"Budget exceeded: {ba.budget_name}",
                        message=(f"Cost ${ba.current_cost:.4f} exceeds ${ba.max_cost:.4f} "
                                 f"({ba.provider_id}, {ba.period})"),
                        source="cost",
                        data={"budget_name": ba.budget_name, "provider_id": ba.provider_id,
                              "current_cost": ba.current_cost, "max_cost": ba.max_cost,
                              "current_tokens": ba.current_tokens, "max_tokens": ba.max_tokens},
                    )
                    count += 1
            except Exception as e:
                logger.warning("Failed to check cost budgets: %s", e)

        if self._performance_tracker:
            try:
                perf_alerts = self._performance_tracker.get_alerts()
                for pa in perf_alerts:
                    sev = AlertSeverity.CRITICAL if pa.severity == "critical" else AlertSeverity.WARNING
                    self.emit(
                        alert_type="performance_regression",
                        severity=sev,
                        title=f"Performance regression: {pa.tool_id}",
                        message=(f"{pa.provider_id}/{pa.model} avg {pa.current_avg:.0f}ms "
                                 f"vs baseline {pa.baseline_avg:.0f}ms ({pa.deviation_pct:+.0f}%)"),
                        source="performance",
                        data={"provider_id": pa.provider_id, "model": pa.model,
                              "tool_id": pa.tool_id, "current_avg": pa.current_avg,
                              "baseline_avg": pa.baseline_avg, "deviation_pct": pa.deviation_pct},
                    )
                    count += 1
            except Exception as e:
                logger.warning("Failed to check performance alerts: %s", e)

        if count > 0:
            logger.info("AlertManager check_all: %d new alert(s)", count)
        return count

    def stats(self) -> Dict[str, Any]:
        total = len(self._alerts)
        unacknowledged = len([a for a in self._alerts if not a.acknowledged])
        by_source: Dict[str, int] = {}
        for a in self._alerts:
            by_source[a.source] = by_source.get(a.source, 0) + 1
        return {
            "total": total,
            "unacknowledged": unacknowledged,
            "by_source": by_source,
            "max_alerts": self._max_alerts,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alerts": [a.to_dict() for a in self._alerts[-50:]],
            "stats": self.stats(),
        }
