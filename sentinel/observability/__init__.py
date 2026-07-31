"""Sentinel Observability — Cross-cutting monitoring, tracing, logging, and recovery.

Architecture:
  ObservabilityEngine
    ├── HealthSystem      (health checks, dependency checks, status)
    ├── MetricsSystem     (collector, registry, aggregation)
    ├── TracingSystem     (TraceID propagation, span tracking)
    ├── LoggingSystem     (structured JSON logging)
    ├── RecoverySystem    (backup, recovery points, rollback)
    └── AlertEngine       (memory, model failures, repeated errors)
"""

from sentinel.observability.health.health_checker import HealthChecker, HealthStatus, HealthState
from sentinel.observability.health.dependency_check import DependencyChecker, DependencyResult
from sentinel.observability.metrics.collector import MetricsCollector, MetricPoint
from sentinel.observability.metrics.registry import MetricRegistry
from sentinel.observability.tracing.trace_manager import TraceManager, SpanContext
from sentinel.observability.logging.structured_logger import StructuredLogger, LogEvent
from sentinel.observability.recovery.backup_manager import BackupManager, BackupRecord
from sentinel.observability.recovery.recovery_manager import RecoveryManager, RecoveryPoint, SystemState
from sentinel.observability.alert_engine import AlertEngine, Alert, AlertLevel, AlertRule

__all__ = [
    "HealthChecker", "HealthStatus", "HealthState",
    "DependencyChecker", "DependencyResult",
    "MetricsCollector", "MetricPoint", "MetricRegistry",
    "TraceManager", "SpanContext",
    "StructuredLogger", "LogEvent",
    "BackupManager", "BackupRecord",
    "RecoveryManager", "RecoveryPoint", "SystemState",
    "AlertEngine", "Alert", "AlertLevel", "AlertRule",
]
