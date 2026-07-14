import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple

from .model_router import TaskType
from .planner import Plan, PlanStep
from .intent import Intent

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    plan: Plan
    hit_count: int = 0
    created_at: str = ""
    last_hit_at: str = ""
    ttl_seconds: int = 300


def _cache_key(intent: Intent) -> str:
    raw = f"{intent.action}|{intent.target}|{json.dumps(intent.parameters, sort_keys=True)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _serialize_plan(plan: Plan) -> dict:
    d = asdict(plan)
    for s in d.get("steps", []):
        md = s.get("model_decision")
        if md:
            tt = md.get("task_type")
            if hasattr(tt, "value"):
                md["task_type"] = tt.value
    return d


def _deserialize_plan(d: dict) -> Plan:
    steps = []
    for sd in d.get("steps", []):
        md = sd.get("model_decision")
        tt = None
        if md:
            tt_str = md.get("task_type")
            if tt_str:
                try:
                    tt = TaskType(tt_str)
                except ValueError:
                    tt = TaskType.QUICK
        from .model_router import RouterDecision

        steps.append(
            PlanStep(
                id=sd.get("id", ""),
                tool_id=sd.get("tool_id", ""),
                params=sd.get("params", {}),
                description=sd.get("description", ""),
                is_reversible=sd.get("is_reversible", False),
                rollback_tool_id=sd.get("rollback_tool_id"),
                rollback_params=sd.get("rollback_params"),
                estimated_impact=sd.get("estimated_impact", "low"),
                estimated_duration_ms=sd.get("estimated_duration_ms"),
                depends_on=sd.get("depends_on", []),
                model_decision=RouterDecision(
                    provider_id=md["provider_id"],
                    model=md["model"],
                    task_type=tt or TaskType.QUICK,
                    strategy=md.get("strategy", "cached"),
                    reason=md.get("reason", "from cache"),
                )
                if md
                else None,
            )
        )
    intent_data = d.get("intent", {})
    intent = Intent(
        action=intent_data.get("action", ""),
        target=intent_data.get("target", ""),
        parameters=intent_data.get("parameters", {}),
        confidence=intent_data.get("confidence", 0.0),
        raw_input=intent_data.get("raw_input", ""),
    )
    return Plan(
        steps=steps,
        intent=intent,
        risk_score=d.get("risk_score", 0.0),
        estimated_duration_ms=d.get("estimated_duration_ms"),
        description=d.get("description", ""),
    )


class PlanCache:
    def __init__(self, max_entries: int = 100, default_ttl: int = 300):
        self._entries: Dict[str, CacheEntry] = {}
        self._max_entries = max_entries
        self._default_ttl = default_ttl
        self._lock = RLock()

    def get(self, intent: Intent) -> Optional[Plan]:
        key = _cache_key(intent)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(entry.last_hit_at)).total_seconds()
            if elapsed >= entry.ttl_seconds:
                del self._entries[key]
                logger.debug("Cache entry expired: %s", key)
                return None
            entry.hit_count += 1
            entry.last_hit_at = datetime.now(timezone.utc).isoformat()
            logger.debug("Plan cache HIT: %s (hits=%d)", key, entry.hit_count)
            return entry.plan

    def set(self, intent: Intent, plan: Plan, ttl: Optional[int] = None) -> None:
        key = _cache_key(intent)
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            if len(self._entries) >= self._max_entries:
                oldest = min(self._entries.keys(), key=lambda k: self._entries[k].last_hit_at)
                del self._entries[oldest]
                logger.debug("Plan cache evicted oldest: %s", oldest)
            self._entries[key] = CacheEntry(
                plan=plan,
                hit_count=0,
                created_at=now,
                last_hit_at=now,
                ttl_seconds=ttl or self._default_ttl,
            )
            logger.debug("Plan cache SET: %s", key)

    def invalidate(self, intent: Intent) -> bool:
        key = _cache_key(intent)
        with self._lock:
            if key in self._entries:
                del self._entries[key]
                logger.debug("Plan cache INVALIDATED: %s", key)
                return True
            return False

    def clear(self) -> int:
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            logger.debug("Plan cache CLEARED (%d entries)", count)
            return count

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "size": len(self._entries),
                "max_entries": self._max_entries,
                "default_ttl_seconds": self._default_ttl,
                "entries": [
                    {
                        "key": k,
                        "hit_count": e.hit_count,
                        "created_at": e.created_at,
                        "last_hit_at": e.last_hit_at,
                        "ttl_seconds": e.ttl_seconds,
                        "description": e.plan.description,
                        "step_count": len(e.plan.steps),
                    }
                    for k, e in sorted(self._entries.items(), key=lambda x: x[1].last_hit_at)
                ],
            }
