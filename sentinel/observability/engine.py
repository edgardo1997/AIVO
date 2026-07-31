"""ObservabilityEngine — Unified facade for all observability subsystems.

This is the single production observability system: health checks, metrics,
distributed tracing, structured logging, backups, recovery and alerts.
It is wired into the Orchestrator and the ToolGateway (request + tool spans).
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
import logging
import time

from sentinel.observability.health.health_checker import HealthChecker, HealthStatus, HealthState, ComponentHealth
from sentinel.observability.health.dependency_check import DependencyChecker, DependencyResult
from sentinel.observability.metrics.collector import MetricsCollector
from sentinel.observability.metrics.registry import MetricRegistry
from sentinel.observability.tracing.trace_manager import TraceManager, SpanContext
from sentinel.observability.logging.structured_logger import StructuredLogger
from sentinel.observability.recovery.backup_manager import BackupManager, BackupRecord
from sentinel.observability.recovery.recovery_manager import RecoveryManager, RecoveryPoint, SystemState
from sentinel.observability.alert_engine import AlertEngine, Alert, AlertRule, AlertLevel

logger = logging.getLogger(__name__)


@dataclass
class ObservabilityConfig:
    health_checks_enabled: bool = True
    metrics_enabled: bool = True
    tracing_enabled: bool = True
    structured_logging_enabled: bool = True
    backup_enabled: bool = True
    recovery_enabled: bool = True
    alerts_enabled: bool = True
    backup_dir: str = "backup"
    max_backups: int = 10
    version: str = "1.0"


class ObservabilityEngine:
    """Central observability facade — wires health, metrics, tracing, logging, recovery, alerts."""

    def __init__(self, config: Optional[ObservabilityConfig] = None):
        self._config = config or ObservabilityConfig()
        self._metric_registry = MetricRegistry()
        self._health_checker = HealthChecker(version=self._config.version)
        self._dependency_checker = DependencyChecker()
        self._metrics_collector = MetricsCollector(self._metric_registry)
        self._trace_manager = TraceManager()
        self._structured_logger = StructuredLogger(trace_manager=self._trace_manager)
        self._backup_manager = BackupManager(backup_dir=self._config.backup_dir, max_backups=self._config.max_backups)
        self._recovery_manager = RecoveryManager(backup_manager=self._backup_manager)
        self._alert_engine = AlertEngine()
        self._active_tool_spans: Dict[str, SpanContext] = {}
        self._setup_default_alerts()
        self._register_default_health()

    # ── Health ───────────────────────────────────────────────────

    def _register_default_health(self) -> None:
        self._health_checker.register("system", lambda: self._health_system())
        self._health_checker.register("metrics", lambda: self._health_metrics())
        self._health_checker.register("tracing", lambda: self._health_tracing())
        self._health_checker.register("database", lambda: self._health_database())
        self._health_checker.register("audit", lambda: self._health_audit())

    def register_component(self, name: str, check_fn: Callable[[], ComponentHealth]) -> None:
        self._health_checker.register(name, check_fn)

    def _health_system(self) -> ComponentHealth:
        try:
            self._metrics_collector.collect_system_metrics()
            mem = self._recent_metric("ram_usage_percent", 0)
            cpu = self._recent_metric("cpu_usage_percent", 0)
            state = HealthState.HEALTHY
            if mem > 95 or cpu > 97:
                state = HealthState.DEGRADED
            return ComponentHealth(name="system", state=state, details={"ram_usage_percent": mem, "cpu_usage_percent": cpu})
        except Exception as e:
            return ComponentHealth(name="system", state=HealthState.DEGRADED, error=str(e)[:200])

    def _health_metrics(self) -> ComponentHealth:
        failed = self._recent_counter("failed_requests")
        total = self._recent_counter("requests_total")
        state = HealthState.HEALTHY
        if total > 20 and failed / total > 0.2:
            state = HealthState.DEGRADED
        return ComponentHealth(name="metrics", state=state, details={"failed_requests": failed, "requests_total": total})

    def _health_tracing(self) -> ComponentHealth:
        summary = self._trace_manager.trace_summary()
        return ComponentHealth(name="tracing", state=HealthState.HEALTHY, details=summary)

    def _health_database(self) -> ComponentHealth:
        state = HealthState.HEALTHY
        if self._recent_counter("database_failures", "database_failure", 0) > 0:
            state = HealthState.DEGRADED
        return ComponentHealth(name="database", state=state, details={"database_failures": self._recent_counter("database_failure")})

    def _health_audit(self) -> ComponentHealth:
        state = HealthState.HEALTHY
        if self._recent_counter("audit_failures", "audit_failure", 0) > 0:
            state = HealthState.DEGRADED
        return ComponentHealth(name="audit", state=state, details={"audit_failures": self._recent_counter("audit_failure")})

    def _recent_metric(self, name: str, default: float = 0.0) -> float:
        gauge = self._metric_registry.gauges.get(name)
        return gauge.value if gauge else default

    def _recent_counter(self, name: str, *alt_names: str, default: float = 0.0) -> float:
        c = self._metric_registry.counters.get(name)
        if c is None:
            for alt in alt_names:
                c = self._metric_registry.counters.get(alt)
                if c is not None:
                    break
        return c.value if c else default

    # ── Alerts ───────────────────────────────────────────────────

    def _setup_default_alerts(self) -> None:
        if not self._config.alerts_enabled:
            return
        self._alert_engine.add_custom_rule(
            "high_memory_usage", "RAM usage > 90%",
            lambda: Alert(name="high_memory_usage", level=AlertLevel.WARNING, message="High memory usage detected", component="system", value=self._recent_metric("ram_usage_percent", 0), threshold=90)
            if self._recent_metric("ram_usage_percent", 0) > 90 else None,
            interval_seconds=30, cooldown_seconds=300,
        )
        self._alert_engine.add_custom_rule(
            "high_cpu_usage", "CPU usage > 95%",
            lambda: Alert(name="high_cpu_usage", level=AlertLevel.WARNING, message="High CPU usage detected", component="system", value=self._recent_metric("cpu_usage_percent", 0), threshold=95)
            if self._recent_metric("cpu_usage_percent", 0) > 95 else None,
            interval_seconds=30, cooldown_seconds=300,
        )
        self._alert_engine.add_custom_rule(
            "model_failure_rate", "Model failure rate > 20%",
            lambda: self._check_model_failure_rate(),
            interval_seconds=60, cooldown_seconds=600,
        )
        self._alert_engine.add_custom_rule(
            "tool_failure_rate", "Tool failure rate > 20%",
            lambda: self._check_tool_failure_rate(),
            interval_seconds=60, cooldown_seconds=600,
        )
        self._alert_engine.add_custom_rule(
            "provider_failure_rate", "Provider failure rate > 30%",
            lambda: self._check_provider_failure_rate(),
            interval_seconds=60, cooldown_seconds=600,
        )
        self._alert_engine.add_custom_rule(
            "consecutive_errors", "5+ consecutive failed requests",
            lambda: self._check_consecutive_errors(),
            interval_seconds=30, cooldown_seconds=300,
        )
        self._alert_engine.add_custom_rule(
            "database_failure", "Database failure detected",
            lambda: self._check_failure_flag("database_failure", "database", "Database failure detected"),
            interval_seconds=30, cooldown_seconds=300,
        )
        self._alert_engine.add_custom_rule(
            "audit_loss", "Audit trail loss detected",
            lambda: self._check_failure_flag("audit_failure", "audit", "Audit trail loss detected"),
            interval_seconds=30, cooldown_seconds=300,
        )

    def _check_model_failure_rate(self) -> Optional[Alert]:
        total = self._metric_registry.counters.get("requests_total")
        failed = self._metric_registry.counters.get("failed_requests")
        if total and failed and total.value > 0:
            rate = failed.value / total.value
            if rate > 0.2:
                return Alert(name="model_failure_rate", level=AlertLevel.WARNING, message=f"Model failure rate: {rate:.0%}", component="model_router", value=rate, threshold=0.2)
        return None

    def _check_tool_failure_rate(self) -> Optional[Alert]:
        failures = self._recent_counter("tool_failures")
        executions = sum(
            int(c.value) for k, c in self._metric_registry.counters.items() if k.startswith("tool_executions")
        )
        if executions >= 5:
            rate = failures / executions
            if rate > 0.2:
                return Alert(name="tool_failure_rate", level=AlertLevel.WARNING, message=f"Tool failure rate: {rate:.0%}", component="tool_gateway", value=rate, threshold=0.2)
        return None

    def _check_provider_failure_rate(self) -> Optional[Alert]:
        failures = self._recent_counter("provider_failures")
        total = self._recent_counter("requests_total")
        if total >= 5:
            rate = failures / total
            if rate > 0.3:
                return Alert(name="provider_failure_rate", level=AlertLevel.WARNING, message=f"Provider failure rate: {rate:.0%}", component="model_router", value=rate, threshold=0.3)
        return None

    def _check_consecutive_errors(self) -> Optional[Alert]:
        consecutive = self._recent_counter("consecutive_errors")
        if consecutive >= 5:
            return Alert(name="consecutive_errors", level=AlertLevel.CRITICAL, message=f"{int(consecutive)} consecutive failed requests", component="pipeline", value=consecutive, threshold=5)
        return None

    def _check_failure_flag(self, counter_name: str, component: str, message: str) -> Optional[Alert]:
        count = self._recent_counter(counter_name)
        if count > 0:
            return Alert(name=counter_name, level=AlertLevel.CRITICAL, message=message, component=component, value=count, threshold=1)
        return None

    # ── Metrics / telemetry ──────────────────────────────────────

    @property
    def health(self) -> HealthChecker:
        return self._health_checker

    @property
    def dependencies(self) -> DependencyChecker:
        return self._dependency_checker

    @property
    def metrics(self) -> MetricsCollector:
        return self._metrics_collector

    @property
    def metric_registry(self) -> MetricRegistry:
        return self._metric_registry

    @property
    def tracer(self) -> TraceManager:
        return self._trace_manager

    @property
    def logger(self) -> StructuredLogger:
        return self._structured_logger

    @property
    def backup(self) -> BackupManager:
        return self._backup_manager

    @property
    def recovery(self) -> RecoveryManager:
        return self._recovery_manager

    @property
    def alerts(self) -> AlertEngine:
        return self._alert_engine

    def record_provider_failure(self, provider_id: str = "unknown") -> None:
        self._metrics_collector.record_provider_failure(provider_id)

    def record_database_failure(self) -> None:
        self._metric_registry.counter("database_failure").inc()

    def record_audit_failure(self) -> None:
        self._metric_registry.counter("audit_failure").inc()

    def record_request(self, model_id: str, success: bool, latency_ms: float) -> None:
        self._metrics_collector.record_request(model_id=model_id, success=success, latency_ms=latency_ms)

    def record_component_duration(self, component: str, duration_ms: float) -> None:
        self._metrics_collector.record_component_duration(component, duration_ms)

    # ── Tool spans (ToolGateway integration) ─────────────────────

    def start_tool_span(self, tool_id: str, execution_id: str = "", parent_span_id: str = "") -> str:
        metadata = {"tool_id": tool_id, "execution_id": execution_id, "parent_span_id": parent_span_id}
        span = self._trace_manager.start_span(component=f"tool:{tool_id}", metadata=metadata)
        self._active_tool_spans[span.span_id] = span
        return span.span_id

    def finish_tool_span(self, span_id: str, success: bool, error_category: str = "", quality=None, policy_decision=None) -> None:
        span = self._active_tool_spans.pop(span_id, None)
        if span is None:
            return
        status = "ok" if success else "error"
        tags = {"success": str(success).lower()}
        if error_category:
            tags["error_category"] = error_category
        if policy_decision is not None:
            tags["policy_decision"] = str(policy_decision)
        self._trace_manager.end_span(span, status=status, tags=tags)
        self._metrics_collector.record_tool_execution(span.metadata.get("tool_id", "unknown"), success, span.duration_ms)

    def start_request_trace(self, request_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> SpanContext:
        span = self._trace_manager.create_context_from_request(request_id=request_id)
        if metadata:
            span.metadata.update(metadata)
        return span

    def end_request_trace(self, span: SpanContext, status: str = "ok") -> None:
        self._trace_manager.end_span(span, status=status)

    def traces(self, limit: int = 100, tool_id: Optional[str] = None) -> List[Dict[str, Any]]:
        all_traces = self._trace_manager.get_all_traces(limit=max(limit, 1))
        result: List[Dict[str, Any]] = []
        for tid, spans in all_traces.items():
            if tool_id:
                matches = [s for s in spans if s.metadata.get("tool_id") == tool_id]
                if not matches:
                    continue
            result.append(
                {
                    "trace_id": tid,
                    "spans": [s.to_dict() for s in sorted(spans, key=lambda s: s.start_time)],
                }
            )
        return result

    def trace_summary(self) -> Dict[str, Any]:
        return self._trace_manager.trace_summary()

    def summary(self) -> Dict[str, Any]:
        return {
            "health": self.check_health().state.value,
            "recovery_state": self._recovery_manager.state.value,
            "total_traces": self._trace_manager.trace_summary().get("total_traces", 0),
            "total_backups": self._backup_manager.count,
            "total_alerts": len(self._alert_engine.recent_alerts()),
        }

    def create_backup(self, source_path: str, label: str = "") -> Optional[BackupRecord]:
        return self._backup_manager.create_backup(source_path, label=label)

    def check_health(self) -> HealthStatus:
        return self._health_checker.check_all()

    def check_dependencies(self) -> DependencyResult:
        return self._dependency_checker.check_all()

    def collect_metrics(self) -> Dict[str, Any]:
        self._metrics_collector.collect_system_metrics()
        return self._metric_registry.snapshot()

    def check_alerts(self) -> List[Alert]:
        fired = self._alert_engine.check()
        for alert in fired:
            self._metrics_collector.record_alert(alert.name, alert.level.value)
        return fired

    # ── Persistence ──────────────────────────────────────────────

    def to_metric_records(self) -> List[Any]:
        """Convert the registry snapshot into MetricRecord rows for the official repo."""
        from sentinel.storage.models import MetricRecord

        records: List[MetricRecord] = []
        snapshot = self._metric_registry.snapshot()
        for key, data in snapshot["counters"].items():
            records.append(MetricRecord(component="observability", metric_name=key, value=float(data["value"]), unit=data.get("unit", "count"), tags=dict(data.get("labels") or {})))
        for key, data in snapshot["gauges"].items():
            records.append(MetricRecord(component="observability", metric_name=key, value=float(data["value"]), unit=data.get("unit", ""), tags=dict(data.get("labels") or {})))
        for key, data in snapshot["histograms"].items():
            records.append(MetricRecord(component="observability", metric_name=key, value=float(data.get("sum", 0)), unit="seconds", tags=dict(data.get("labels") or {})))
        return records

    # ── Dashboard ────────────────────────────────────────────────

    def get_dashboard(self) -> Dict[str, Any]:
        health_status = self.check_health()
        metrics_snapshot = self.collect_metrics()
        return {
            "health": health_status.to_dict(),
            "metrics": metrics_snapshot,
            "models": self._metrics_collector.model_metrics(),
            "recovery": self._recovery_manager.summary(),
            "alerts": self._alert_engine.summary(),
            "traces": self._trace_manager.trace_summary(),
        }
