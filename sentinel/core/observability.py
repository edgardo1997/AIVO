from __future__ import annotations

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

    def start(self, tool_id: str, execution_id: str = "", parent_id: str = "") -> str:
        span_id = uuid.uuid4().hex[:16]
        with self._lock:
            self._active[span_id] = {
                "trace_id": execution_id or uuid.uuid4().hex,
                "span_id": span_id,
                "parent_id": parent_id or None,
                "tool_id": tool_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "_started_monotonic": time.monotonic(),
            }
        return span_id

    def finish(
        self, span_id: str, success: bool, error_category: Optional[str] = None,
        quality: Optional[Dict[str, Any]] = None, policy_decision: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            span = self._active.pop(span_id, None)
            if span is None:
                return None
            started = span.pop("_started_monotonic")
            span.update({
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "success": bool(success),
                "error_category": error_category,
                "policy_decision": policy_decision,
                "quality": quality or {"passed": True, "redacted": False, "issues": []},
            })
            self._traces.append(span)
            return dict(span)

    def traces(self, limit: int = 100, tool_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            rows = list(reversed(self._traces))
        if tool_id:
            rows = [row for row in rows if row["tool_id"] == tool_id]
        return [dict(row) for row in rows[:max(1, min(limit, 500))]]

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
            "latency_ms": {"average": round(mean(durations), 2) if durations else 0.0,
                           "p50": percentile(0.50), "p95": percentile(0.95),
                           "maximum": round(max(durations), 2) if durations else 0.0},
            "quality": {"blocked": quality_blocks, "redacted": redactions},
            "errors_by_category": dict(categories),
        }
