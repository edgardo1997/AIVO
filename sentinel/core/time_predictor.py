"""Time Predictor.

Estimates how long a task will take based on historical data,
task type, model, hardware, and complexity.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from math import sqrt
from statistics import mean, stdev
from typing import Any, Dict, List, Optional

from sentinel.core.performance_intelligence import PerformanceIntelligence

logger = logging.getLogger(__name__)


@dataclass
class TimePrediction:
    estimated_seconds: float
    confidence: float
    min_estimate: float
    max_estimate: float
    sample_count: int
    model_id: str
    task_type: str
    complexity_factor: float = 1.0

    @property
    def estimated_display(self) -> str:
        if self.estimated_seconds < 60:
            return f"{self.estimated_seconds:.0f} seconds"
        elif self.estimated_seconds < 3600:
            minutes = self.estimated_seconds / 60
            return f"{minutes:.1f} minutes"
        else:
            hours = self.estimated_seconds / 3600
            return f"{hours:.1f} hours"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "estimated_seconds": self.estimated_seconds,
            "estimated_display": self.estimated_display,
            "confidence": self.confidence,
            "min_estimate": self.min_estimate,
            "max_estimate": self.max_estimate,
            "sample_count": self.sample_count,
            "model_id": self.model_id,
            "task_type": self.task_type,
            "complexity_factor": self.complexity_factor,
        }


class TimePredictor:
    def __init__(self, performance_intelligence: Optional[PerformanceIntelligence] = None):
        self._perf = performance_intelligence

    def predict(
        self,
        model_id: str,
        task_type: str,
        complexity_hint: Optional[str] = None,
        estimated_tokens: Optional[int] = None,
    ) -> TimePrediction:
        if self._perf is None:
            return TimePrediction(
                estimated_seconds=10.0,
                confidence=0.1,
                min_estimate=5.0,
                max_estimate=30.0,
                sample_count=0,
                model_id=model_id,
                task_type=task_type,
            )

        metrics = self._perf.get_metrics(model_id=model_id)
        relevant = [m for m in metrics if m.task_type == task_type]
        all_model = [m for m in metrics]

        if relevant:
            latencies = [m.latency for m in relevant]
            samples = len(latencies)
            avg = mean(latencies)
            std = stdev(latencies) if len(latencies) > 1 else avg * 0.5
        elif all_model:
            latencies = [m.latency for m in all_model]
            samples = len(latencies)
            avg = mean(latencies)
            std = stdev(latencies) if len(latencies) > 1 else avg * 0.5
        else:
            return TimePrediction(
                estimated_seconds=10.0,
                confidence=0.1,
                min_estimate=5.0,
                max_estimate=30.0,
                sample_count=0,
                model_id=model_id,
                task_type=task_type,
            )

        complexity_factor = self._resolve_complexity(complexity_hint)
        if estimated_tokens and avg > 0:
            avg_tokens = mean(m.tokens_used for m in (relevant or all_model)) or 1
            token_ratio = estimated_tokens / avg_tokens
            complexity_factor *= max(0.1, min(10.0, token_ratio))

        adjusted_avg = avg * complexity_factor

        confidence = min(0.95, max(0.1, 1.0 - (std / max(avg, 0.01)) / sqrt(max(samples, 1))))
        confidence = round(confidence, 2)

        margin = std * 1.96 / sqrt(max(samples, 1))
        min_est = max(0, adjusted_avg - margin)
        max_est = adjusted_avg + margin

        return TimePrediction(
            estimated_seconds=round(adjusted_avg, 1),
            confidence=confidence,
            min_estimate=round(min_est, 1),
            max_estimate=round(max_est, 1),
            sample_count=samples,
            model_id=model_id,
            task_type=task_type,
            complexity_factor=round(complexity_factor, 2),
        )

    def predict_by_complexity(
        self, model_id: str, task_type: str, line_count: Optional[int] = None
    ) -> TimePrediction:
        complexity = None
        if line_count:
            if line_count < 100:
                complexity = "simple"
            elif line_count < 1000:
                complexity = "moderate"
            elif line_count < 10000:
                complexity = "complex"
            else:
                complexity = "very_complex"
        return self.predict(model_id, task_type, complexity_hint=complexity)

    @staticmethod
    def _resolve_complexity(hint: Optional[str]) -> float:
        factors = {
            "simple": 0.5,
            "quick": 0.5,
            "moderate": 1.0,
            "normal": 1.0,
            "complex": 2.0,
            "very_complex": 4.0,
            "analysis": 1.5,
            "coding": 2.0,
            "reasoning": 1.5,
        }
        if hint is None:
            return 1.0
        key = hint.lower().strip()
        return factors.get(key, 1.0)
