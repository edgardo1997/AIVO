import threading
import time
import uuid
from collections import Counter, deque
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Dict, List, Optional


class ObservabilityService:
    """Bounded, privacy-preserving execution traces and aggregate metrics."""

    def __init__(self, max_traces: int = 1000):
        self._traces = deque(maxlen=max_traces)
        self._active: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._span_counter = Counter()
        self._error_counter = Counter()
        self._latencies: Dict[str, List[float]] = {}
        self._health_status: Dict[str, bool] = {}

    def start(self, tool_id: str, execution_id: str = "", parent_id: str = "") -> str:
        span_id = uuid.uuid4().hex[:16]
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._active[span_id] = {
                "trace_id": execution_id or uuid.uuid4().hex,
                "span_id": span_id,
                "parent_id": parent_id or None,
                "tool_id": tool_id,
                "started_at": now,
                "_started_monotonic": time.monotonic(),
            }
            self._span_counter[tool_id] += 1
        return span_id

    def finish(
        self,
        span_id: str,
        success: bool,
        error_category: Optional[str] = None,
        quality: Optional[Dict[str, Any]] = None,
        policy_decision: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            span = self._active.pop(span_id, None)
            if span is None:
                return None
            started = span.pop("_started_monotonic")
            duration = round((time.monotonic() - started) * 1000, 2)
            span.update(
                {
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "duration_ms": duration,
                    "success": bool(success),
                    "error_category": error_category,
                    "policy_decision": policy_decision,
                    "quality": quality or {"passed": True, "redacted": False, "issues": []},
                }
            )
            self._traces.append(span)
            tool = span["tool_id"]
            self._latencies.setdefault(tool, []).append(duration)
            if not success:
                self._error_counter[error_category or "unknown"] += 1
            if error_category:
                self._health_status[f"{tool}:{error_category}"] = False
            else:
                self._health_status[tool] = True
            return dict(span)

    def traces(self, limit: int = 100, tool_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            rows = list(reversed(self._traces))
        if tool_id:
            rows = [row for row in rows if row["tool_id"] == tool_id]
        return [dict(row) for row in rows[: max(1, min(limit, 500))]]

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            rows = list(self._traces)
            active = len(self._active)
        durations = sorted(float(row["duration_ms"]) for row in rows)
        total = len(rows)
        failures = sum(not row["success"] for row in rows)
        redactions = sum(bool(row.get("quality", {}).get("redacted")) for row in rows)
        quality_blocks = sum(not bool(row.get("quality", {}).get("passed", True)) for row in rows)
        categories = Counter(row.get("error_category") for row in rows if row.get("error_category"))

        def percentile(p: float) -> float:
            if not durations:
                return 0.0
            index = min(len(durations) - 1, int((len(durations) - 1) * p))
            return round(durations[index], 2)

        return {
            "total_executions": total,
            "active_spans": active,
            "success_rate": round(((total - failures) / total * 100), 2) if total else 100.0,
            "latency_ms": {
                "average": round(mean(durations), 2) if durations else 0.0,
                "p50": percentile(0.50),
                "p95": percentile(0.95),
                "maximum": round(max(durations), 2) if durations else 0.0,
            },
            "quality": {"blocked": quality_blocks, "redacted": redactions},
            "errors_by_category": dict(categories),
        }

    def health(self) -> Dict[str, Any]:
        """Returns a health-check compatible status summary."""
        with self._lock:
            rows = list(self._traces)
            active = len(self._active)
        recent = [r for r in rows if r.get("finished_at")]
        recent_failures = sum(1 for r in recent[-50:] if not r["success"]) if recent else 0
        recent_total = min(len(recent), 50)
        failure_rate = round(recent_failures / recent_total * 100, 2) if recent_total else 0.0
        degraded = failure_rate > 20.0 or active > 100
        return {
            "status": "degraded" if degraded else "healthy",
            "active_spans": active,
            "recent_executions": recent_total,
            "recent_failure_rate_pct": failure_rate,
            "total_executions": len(rows),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def span_tree(self, trace_id: str) -> List[Dict[str, Any]]:
        """Build a tree of spans for a given trace_id (distributed trace support)."""
        with self._lock:
            spans = [r for r in self._traces if r.get("trace_id") == trace_id]
        roots = [s for s in spans if not s.get("parent_id")]
        children = [s for s in spans if s.get("parent_id")]
        tree = []
        for root in roots:
            node = dict(root)
            node["children"] = [dict(c) for c in children if c.get("parent_id") == root["span_id"]]
            tree.append(node)
        return tree

    def trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Get a full trace by trace_id including all spans."""
        spans = self.span_tree(trace_id)
        if not spans:
            return None
        return {
            "trace_id": trace_id,
            "spans": spans,
            "total_spans": len(spans),
            "total_duration_ms": sum(s.get("duration_ms", 0) for s in spans),
        }
