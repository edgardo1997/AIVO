"""Central metric registry — stores and aggregates named counters and histograms.

Labeled metrics are keyed by (name + canonical labels) so each label combination
gets its own Counter/Gauge/Histogram. Unlabeled metrics keep their plain name key.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import threading
import time


@dataclass
class Counter:
    name: str
    value: float = 0.0
    unit: str = "count"
    labels: Dict[str, str] = field(default_factory=dict)

    def inc(self, amount: float = 1.0) -> None:
        self.value += amount

    def set(self, value: float) -> None:
        self.value = value


@dataclass
class Gauge:
    name: str
    value: float = 0.0
    unit: str = ""
    labels: Dict[str, str] = field(default_factory=dict)

    def set(self, v: float) -> None:
        self.value = v


@dataclass
class Histogram:
    name: str
    buckets: List[float] = field(default_factory=lambda: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0])
    counts: Dict[int, int] = field(default_factory=dict)
    sum_: float = 0.0
    count: int = 0
    unit: str = "seconds"
    labels: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not self.counts:
            self.counts = {i: 0 for i in range(len(self.buckets))}

    def observe(self, value: float) -> None:
        self.count += 1
        self.sum_ += value
        for i, b in enumerate(self.buckets):
            if value <= b:
                self.counts[i] = self.counts.get(i, 0) + 1
                break

    @property
    def mean(self) -> float:
        return self.sum_ / max(self.count, 1)

    @property
    def percentiles(self) -> Dict[str, float]:
        if self.count == 0:
            return {"p50": 0.0, "p90": 0.0, "p99": 0.0}
        sorted_vals = [b for b in self.buckets]
        return {
            "p50": sorted_vals[min(len(sorted_vals) - 1, int(self.count * 0.5))] if self.count > 0 else 0,
            "p90": sorted_vals[min(len(sorted_vals) - 1, int(self.count * 0.9))] if self.count > 0 else 0,
            "p99": sorted_vals[min(len(sorted_vals) - 1, int(self.count * 0.99))] if self.count > 0 else 0,
        }


class MetricRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}

    @staticmethod
    def _key(name: str, labels: Optional[Dict[str, str]]) -> str:
        """Stable composite key: plain name when unlabeled, else name{k=v,...}."""
        if not labels:
            return name
        parts = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{parts}}}"

    def counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> Counter:
        key = self._key(name, labels)
        with self._lock:
            if key not in self._counters:
                self._counters[key] = Counter(name=name, labels=labels or {})
            return self._counters[key]

    def gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> Gauge:
        key = self._key(name, labels)
        with self._lock:
            if key not in self._gauges:
                self._gauges[key] = Gauge(name=name, labels=labels or {})
            return self._gauges[key]

    def histogram(self, name: str, labels: Optional[Dict[str, str]] = None) -> Histogram:
        key = self._key(name, labels)
        with self._lock:
            if key not in self._histograms:
                self._histograms[key] = Histogram(name=name, labels=labels or {})
            return self._histograms[key]

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "counters": {k: {"value": v.value, "unit": v.unit, "labels": v.labels} for k, v in self._counters.items()},
                "gauges": {k: {"value": v.value, "unit": v.unit, "labels": v.labels} for k, v in self._gauges.items()},
                "histograms": {
                    k: {"count": v.count, "sum": round(v.sum_, 4), "mean": round(v.mean, 4), "percentiles": v.percentiles, "unit": v.unit, "labels": v.labels}
                    for k, v in self._histograms.items()
                },
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()

    @property
    def counters(self) -> Dict[str, Counter]:
        return dict(self._counters)

    @property
    def gauges(self) -> Dict[str, Gauge]:
        return dict(self._gauges)

    @property
    def histograms(self) -> Dict[str, Histogram]:
        return dict(self._histograms)
