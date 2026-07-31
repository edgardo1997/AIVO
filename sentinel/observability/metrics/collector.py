"""Metrics collector — pulls system and application metrics into the registry."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import logging
import platform
import time

from sentinel.observability.metrics.registry import MetricRegistry

logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    name: str
    value: float
    unit: str = ""
    labels: Dict[str, str] = None
    timestamp: float = 0.0

    def __post_init__(self):
        if self.labels is None:
            self.labels = {}
        if not self.timestamp:
            self.timestamp = time.time()


class MetricsCollector:
    def __init__(self, registry: MetricRegistry):
        self._registry = registry
        self._system_providers: Dict[str, Any] = {}
        self._start_time = time.monotonic()

    def record_request(self, model_id: str = "unknown", success: bool = True, latency_ms: float = 0.0) -> None:
        self._registry.counter("requests_total").inc()
        label = "success" if success else "failure"
        self._registry.counter("requests_by_status", {"status": label, "model": model_id}).inc()
        self._registry.counter("model_usage", {"model": model_id}).inc()
        self._registry.histogram("request_latency_ms", {"model": model_id}).observe(latency_ms / 1000.0)
        if not success:
            self._registry.counter("failed_requests").inc()
            self._registry.counter("consecutive_errors").inc()
        else:
            self._registry.counter("consecutive_errors").set(0)

    def record_component_duration(self, component: str, duration_ms: float) -> None:
        self._registry.histogram("component_duration", {"component": component}).observe(duration_ms / 1000.0)

    def record_tool_execution(self, tool_id: str, success: bool, duration_ms: float) -> None:
        status = "success" if success else "failure"
        self._registry.counter("tool_executions", {"tool": tool_id, "status": status}).inc()
        self._registry.histogram("tool_duration", {"tool": tool_id}).observe(duration_ms / 1000.0)
        if not success:
            self._registry.counter("tool_failures", {"tool": tool_id}).inc()

    def record_provider_failure(self, provider_id: str = "unknown") -> None:
        self._registry.counter("provider_failures", {"provider": provider_id}).inc()
        self._registry.counter("consecutive_errors").inc()

    def record_alert(self, alert_name: str, level: str) -> None:
        self._registry.counter("alerts_total", {"name": alert_name, "level": level}).inc()

    def set_system_gauge(self, name: str, value: float, unit: str = "") -> None:
        self._registry.gauge(name, {"unit": unit}).set(value)

    def collect_system_metrics(self) -> None:
        try:
            import psutil
            self.set_system_gauge("cpu_usage_percent", psutil.cpu_percent(interval=0.1), "%")
            mem = psutil.virtual_memory()
            self.set_system_gauge("ram_usage_percent", mem.percent, "%")
            self.set_system_gauge("ram_used_gb", mem.used / (1024**3), "GB")
            self.set_system_gauge("ram_total_gb", mem.total / (1024**3), "GB")
            disk = psutil.disk_usage("/")
            self.set_system_gauge("disk_usage_percent", disk.percent, "%")
            self.set_system_gauge("disk_free_gb", disk.free / (1024**3), "GB")
            net = psutil.net_io_counters()
            self.set_system_gauge("network_bytes_sent", net.bytes_sent, "bytes")
            self.set_system_gauge("network_bytes_recv", net.bytes_recv, "bytes")
            self.set_system_gauge("process_count", len(psutil.pids()), "count")
        except ImportError:
            pass
        except Exception as e:
            logger.debug("System metrics collection failed: %s", e)

    def model_metrics(self) -> Dict[str, Dict[str, Any]]:
        models: Dict[str, Dict[str, Any]] = {}
        for key, c in self._registry.counters.items():
            if key.startswith("model_usage"):
                model = _parse_label(key, "model")
                if model not in models:
                    models[model] = {"requests": 0, "avg_latency": 0.0, "success_rate": 1.0}
                models[model]["requests"] = int(c.value)
        for key, h in self._registry.histograms.items():
            if key.startswith("request_latency_ms"):
                model = _parse_label(key, "model")
                if model not in models:
                    models[model] = {"requests": 0, "avg_latency": 0.0, "success_rate": 1.0}
                models[model]["avg_latency"] = round(h.mean * 1000, 1)
        success_counts: Dict[str, int] = {}
        failure_counts: Dict[str, int] = {}
        for key, c in self._registry.counters.items():
            if key.startswith("requests_by_status"):
                model = _parse_label(key, "model")
                status = _parse_label(key, "status")
                if status == "success":
                    success_counts[model] = int(c.value)
                elif status == "failure":
                    failure_counts[model] = int(c.value)
        all_models = set(list(models.keys()) + list(success_counts.keys()) + list(failure_counts.keys()))
        for m in all_models:
            if m not in models:
                models[m] = {"requests": 0, "avg_latency": 0.0, "success_rate": 1.0}
            total = success_counts.get(m, 0) + failure_counts.get(m, 0)
            models[m]["success_rate"] = round(success_counts.get(m, 0) / max(total, 1), 2)
        return models

    def summary(self) -> Dict[str, Any]:
        self.collect_system_metrics()
        snapshot = self._registry.snapshot()
        snapshot["models"] = self.model_metrics()
        snapshot["uptime_seconds"] = time.monotonic() - self._start_time
        return snapshot


def _parse_label(key: str, label_key: str) -> str:
    """Extract one label value from a composite registry key 'name{k=v,...}'."""
    start = key.find("{")
    if start < 0:
        return "unknown"
    body = key[start + 1 : key.rfind("}")]
    for part in body.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            if k == label_key:
                return v
    return "unknown"
