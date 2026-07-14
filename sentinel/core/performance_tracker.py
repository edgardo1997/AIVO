import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import mean, stdev
from typing import Any, Dict, List, Optional, Tuple

from .model_router import TaskType

logger = logging.getLogger(__name__)

REGRESSION_THRESHOLD_PCT = 50.0
CRITICAL_THRESHOLD_PCT = 100.0
BASELINE_SAMPLES = 10


@dataclass
class DurationRecord:
    provider_id: str
    model: str
    task_type: TaskType
    tool_id: str
    duration_ms: float
    success: bool
    timestamp: str = ""


@dataclass
class PerformanceBaseline:
    provider_id: str
    model: str
    task_type: TaskType
    tool_id: str
    avg_duration_ms: float
    std_duration_ms: float
    sample_count: int
    min_duration_ms: float
    max_duration_ms: float


@dataclass
class RegressionAlert:
    provider_id: str
    model: str
    task_type: TaskType
    tool_id: str
    baseline_avg: float
    current_avg: float
    deviation_pct: float
    severity: str
    timestamp: str = ""


class PerformanceTracker:
    def __init__(self, max_records_per_key: int = 1000):
        self._records: Dict[Tuple[str, str, str, str], deque] = defaultdict(lambda: deque(maxlen=max_records_per_key))
        self._alerts: List[RegressionAlert] = []
        self._max_records = max_records_per_key
        self._total_records = 0

    def _key(self, provider_id: str, model: str, task_type: TaskType, tool_id: str) -> Tuple[str, str, str, str]:
        return (provider_id, model, task_type.value, tool_id)

    def record(
        self,
        provider_id: str,
        model: str,
        task_type: TaskType,
        tool_id: str,
        duration_ms: float,
        success: bool,
    ) -> Optional[RegressionAlert]:
        ts = datetime.now(timezone.utc).isoformat()
        rec = DurationRecord(
            provider_id=provider_id,
            model=model,
            task_type=task_type,
            tool_id=tool_id,
            duration_ms=duration_ms,
            success=success,
            timestamp=ts,
        )
        key = self._key(provider_id, model, task_type, tool_id)
        self._records[key].append(rec)
        self._total_records += 1

        alert = self._check_regression(key)
        if alert:
            self._alerts.append(alert)
        return alert

    def _check_regression(self, key: Tuple[str, str, str, str]) -> Optional[RegressionAlert]:
        records = list(self._records[key])
        if len(records) < BASELINE_SAMPLES + 1:
            return None

        baseline_records = records[:BASELINE_SAMPLES]
        current_records = records[BASELINE_SAMPLES:]

        baseline_avg = mean(r.duration_ms for r in baseline_records)
        current_avg = mean(r.duration_ms for r in current_records)

        if baseline_avg <= 0:
            return None

        deviation_pct = ((current_avg - baseline_avg) / baseline_avg) * 100.0

        if deviation_pct <= REGRESSION_THRESHOLD_PCT:
            return None

        severity = "critical" if deviation_pct >= CRITICAL_THRESHOLD_PCT else "warning"
        last = records[-1]

        return RegressionAlert(
            provider_id=last.provider_id,
            model=last.model,
            task_type=last.task_type,
            tool_id=last.tool_id,
            baseline_avg=round(baseline_avg, 1),
            current_avg=round(current_avg, 1),
            deviation_pct=round(deviation_pct, 1),
            severity=severity,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def get_baselines(self) -> List[PerformanceBaseline]:
        result = []
        for key, records in self._records.items():
            provider_id, model, tt_str, tool_id = key
            try:
                tt = TaskType(tt_str)
            except ValueError:
                continue
            recs = list(records)
            durations = [r.duration_ms for r in recs]
            if len(durations) < 2:
                continue
            result.append(
                PerformanceBaseline(
                    provider_id=provider_id,
                    model=model,
                    task_type=tt,
                    tool_id=tool_id,
                    avg_duration_ms=round(mean(durations), 1),
                    std_duration_ms=round(stdev(durations), 1) if len(durations) > 1 else 0.0,
                    sample_count=len(durations),
                    min_duration_ms=min(durations),
                    max_duration_ms=max(durations),
                )
            )
        result.sort(key=lambda b: b.avg_duration_ms, reverse=True)
        return result

    def get_alerts(self, severity: Optional[str] = None) -> List[RegressionAlert]:
        if severity:
            return [a for a in self._alerts if a.severity == severity]
        return list(self._alerts)

    @property
    def total_records(self) -> int:
        return self._total_records
