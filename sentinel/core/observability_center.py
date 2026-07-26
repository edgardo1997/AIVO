"""Observability Center — unified dashboard for health, traces, metrics, and logs.

Aggregates data from ObservabilityService, PipelineMetricsService, RateLimiter,
and PolicyEngine into a single consumable view for monitoring and debugging.
"""

from typing import Any, Dict, Optional


class ObservabilityCenter:
    """Unified observability dashboard aggregating metrics, health, traces, and logs."""

    def __init__(self, observability=None, pipeline_metrics=None, rate_limiter=None, policy_engine=None):
        self._observability = observability
        self._pipeline_metrics = pipeline_metrics
        self._rate_limiter = rate_limiter
        self._policy_engine = policy_engine

    def set_observability(self, service) -> None:
        self._observability = service

    def set_pipeline_metrics(self, service) -> None:
        self._pipeline_metrics = service

    def set_rate_limiter(self, limiter) -> None:
        self._rate_limiter = limiter

    def set_policy_engine(self, engine) -> None:
        self._policy_engine = engine

    def dashboard(self) -> Dict[str, Any]:
        """Aggregated health and performance snapshot."""
        health = self._observability.health() if self._observability else {"status": "unavailable"}
        summary = self._observability.summary() if self._observability else {}
        pipeline = self._pipeline_metrics.summary() if self._pipeline_metrics else {}
        rate_stats = self._rate_limiter.stats() if self._rate_limiter else {}
        policy_stats = self._policy_engine.audit_summary() if self._policy_engine else {}

        return {
            "status": health.get("status", "unknown"),
            "health": health,
            "execution": {
                "total": summary.get("total_executions", 0),
                "success_rate": summary.get("success_rate", 100.0),
                "active_spans": summary.get("active_spans", 0),
                "latency_ms": summary.get("latency_ms", {}),
            },
            "pipeline": pipeline,
            "rate_limiter": {
                "active_keys": rate_stats.get("active_keys", 0),
                "consumption": rate_stats.get("consumption", {}),
                "token_buckets": rate_stats.get("token_buckets", {}),
            },
            "policy_engine": policy_stats,
            "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }

    def component_status(self) -> Dict[str, str]:
        """Per-component health status."""
        status: Dict[str, str] = {}
        if self._observability:
            h = self._observability.health()
            status["observability"] = h.get("status", "unknown")
        else:
            status["observability"] = "disconnected"
        status["pipeline_metrics"] = "connected" if self._pipeline_metrics else "disconnected"
        status["rate_limiter"] = "connected" if self._rate_limiter else "disconnected"
        status["policy_engine"] = "connected" if self._policy_engine else "disconnected"
        return status
