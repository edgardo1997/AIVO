"""Allowlisted aggregation of metrics from canary-only components."""

from dataclasses import dataclass


@dataclass(frozen=True)
class StabilityMetrics:
    total_events: int
    processed_events: int
    ignored_events: int
    dropped_events: int
    average_latency_ms: float
    max_latency_ms: float
    latency_percentiles: dict[str, float]
    memory_start: float
    memory_current: float
    memory_delta: float
    total_errors: int
    consecutive_errors: int
    error_rate: float
    comparison_matches: int
    comparison_divergences: int
    conversion_failures: int
    observer_stable: bool = True


class StabilityCollector:
    """Combine numeric summaries without retaining source dictionaries."""

    _COMPONENTS = {
        "runtime_canary",
        "canary_observation",
        "policy_v2_shadow",
        "application_discovery_v2",
        "authorization_canary",
        "cutover_validation",
    }

    def collect(
        self,
        component_metrics: dict[str, dict[str, int | float | bool | dict]],
    ) -> StabilityMetrics:
        unknown = set(component_metrics) - self._COMPONENTS
        if unknown:
            raise ValueError("unsupported stability metric component")
        observation = component_metrics.get("canary_observation", {})
        runtime = component_metrics.get("runtime_canary", {})
        total_events = int(observation.get("total_events", 0))
        total_errors = int(observation.get("total_errors", 0))
        memory_start = float(observation.get("memory_start", 0.0))
        memory_current = float(observation.get("memory_current", 0.0))
        percentiles = observation.get("latency_percentiles", {})
        safe_percentiles = (
            {key: float(percentiles.get(key, 0.0)) for key in ("p50", "p95", "p99")}
            if isinstance(percentiles, dict)
            else {
                "p50": 0.0,
                "p95": 0.0,
                "p99": 0.0,
            }
        )
        return StabilityMetrics(
            total_events=total_events,
            processed_events=int(observation.get("processed_events", 0)),
            ignored_events=int(observation.get("ignored_events", 0)),
            dropped_events=int(observation.get("dropped_events", 0)),
            average_latency_ms=float(observation.get("average_latency_ms", 0.0)),
            max_latency_ms=float(observation.get("max_latency_ms", 0.0)),
            latency_percentiles=safe_percentiles,
            memory_start=memory_start,
            memory_current=memory_current,
            memory_delta=memory_current - memory_start,
            total_errors=total_errors,
            consecutive_errors=int(observation.get("consecutive_errors", 0)),
            error_rate=(total_errors / total_events if total_events > 0 else 0.0),
            comparison_matches=int(runtime.get("comparison_matches", 0)),
            comparison_divergences=int(runtime.get("comparison_divergences", 0)),
            conversion_failures=int(runtime.get("conversion_failures", 0)),
            observer_stable=bool(observation.get("observer_stable", True)),
        )
