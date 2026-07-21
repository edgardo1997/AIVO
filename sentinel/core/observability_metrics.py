"""Pipeline metrics derived from EventStore — durations, throughput, failures, bottlenecks."""

import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple

from sentinel.core.event_store import EventStore
from sentinel.core.events import SentinelEvent

log = logging.getLogger(__name__)

_COMPONENT_LABELS = {
    "context_engine": "Context",
    "intent_engine": "Intent",
    "planner": "Planner",
    "policy_engine": "Policy",
    "tool_gateway": "Tool",
    "execution": "Execution",
    "audit": "Audit",
    "pipeline": "Pipeline",
}


class PipelineMetricsService:
    def __init__(self, event_store: EventStore):
        self._store = event_store

    def summary(self) -> Dict[str, Any]:
        stats = self._store.stats()
        return {
            "total_events": stats["total_events"],
            "total_failures": stats["failed_count"],
        }

    def component_durations(self, limit: int = 50) -> List[Dict[str, Any]]:
        components: Dict[str, List[float]] = defaultdict(list)
        for event in self._recent_events(limit):
            if event.duration is not None and event.component:
                components[event.component].append(event.duration)
        result = []
        for comp, durations in sorted(components.items(), key=lambda x: -mean(x[1]) if x[1] else 0):
            result.append({
                "component": comp,
                "label": _COMPONENT_LABELS.get(comp, comp),
                "avg_duration_ms": round(mean(durations) * 1000, 2),
                "max_duration_ms": round(max(durations) * 1000, 2),
                "sample_count": len(durations),
            })
        return result

    def tool_usage(self, limit: int = 10) -> List[Dict[str, Any]]:
        counter: Counter[str] = Counter()
        failures: Counter[str] = Counter()
        for event in self._recent_events():
            if event.tool:
                counter[event.tool] += 1
                if event.status == "failed":
                    failures[event.tool] += 1
        total = sum(counter.values()) or 1
        result = []
        for tool, count in counter.most_common(limit):
            fail_count = failures.get(tool, 0)
            result.append({
                "tool": tool,
                "calls": count,
                "share_pct": round(count / total * 100, 1),
                "failures": fail_count,
                "failure_rate": round(fail_count / count * 100, 1),
            })
        return result

    def throughput(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).timestamp()
        window = 300
        recent = 0
        for event in self._recent_events():
            if event.event_type in ("pipeline.started", "execution.started") and event.timestamp >= now - window:
                recent += 1
        return {
            "requests_per_minute": round(recent / (window / 60), 1),
            "window_seconds": window,
        }

    def bottlenecks(self, limit: int = 5) -> List[Dict[str, Any]]:
        durations = self.component_durations(limit=100)
        scored = []
        for d in durations:
            if d["sample_count"] < 2:
                continue
            failure_rate = 0.0
            for t in self.tool_usage(limit=50):
                if t["tool"].startswith(d["component"].replace("_", ".")):
                    failure_rate = t["failure_rate"]
                    break
            bottleneck_score = d["avg_duration_ms"] * (1 + failure_rate / 100)
            scored.append({**d, "bottleneck_score": round(bottleneck_score, 2), "failure_rate": failure_rate})
        scored.sort(key=lambda x: -x["bottleneck_score"])
        return scored[:limit]

    def timeline(self, request_id: str) -> Dict[str, Any]:
        events = self._store.get_timeline(request_id)
        tree: Dict[str, Any] = {"request_id": request_id, "children": []}
        component_groups: Dict[str, List[SentinelEvent]] = defaultdict(list)
        for event in events:
            component_groups[event.component or "unknown"].append(event)
        for comp in ("pipeline", "context_engine", "intent_engine", "planner", "policy_engine", "tool_gateway", "execution", "audit"):
            group = component_groups.pop(comp, [])
            if not group:
                continue
            node: Dict[str, Any] = {
                "component": comp,
                "label": _COMPONENT_LABELS.get(comp, comp),
                "events": [self._event_summary(e) for e in group],
                "duration_ms": self._span_duration(group),
                "status": self._span_status(group),
            }
            tree["children"].append(node)
        for comp, group in component_groups.items():
            tree["children"].append({
                "component": comp,
                "label": comp,
                "events": [self._event_summary(e) for e in group],
                "duration_ms": self._span_duration(group),
                "status": self._span_status(group),
            })
        return tree

    def _recent_events(self, limit: int = 500) -> List[SentinelEvent]:
        try:
            return self._store.query("")[:limit]
        except Exception:
            return []

    def _event_summary(self, event: SentinelEvent) -> Dict[str, Any]:
        return {
            "event_type": event.event_type,
            "status": event.status,
            "timestamp": event.timestamp,
            "tool": event.tool,
            "message": event.message,
            "duration": event.duration,
            "progress": event.progress,
        }

    def _span_duration(self, events: List[SentinelEvent]) -> float:
        durations = [e.duration for e in events if e.duration is not None]
        if durations:
            return round(sum(durations) / len(durations) * 1000, 2)
        if len(events) >= 2:
            return round((events[-1].timestamp - events[0].timestamp) * 1000, 2)
        return 0.0

    def _span_status(self, events: List[SentinelEvent]) -> str:
        for e in reversed(events):
            if e.status in ("failed", "completed", "error"):
                return e.status
        return "unknown"
