from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import time
import asyncio
import logging

from sentinel.intelligence.confidence_scorer import ConfidenceScorer, ConfidenceScore

logger = logging.getLogger(__name__)


@dataclass
class ModelResponse:
    model_id: str = ""
    provider: str = ""
    task_id: str = ""
    task_name: str = ""
    response_text: str = ""
    duration_ms: float = 0.0
    token_count: int = 0
    cost: float = 0.0
    success: bool = True
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "task_id": self.task_id,
            "task_name": self.task_name,
            "response_text": self.response_text[:500],
            "duration_ms": self.duration_ms,
            "token_count": self.token_count,
            "cost": self.cost,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class EvaluatedResponse:
    response: ModelResponse
    confidence: ConfidenceScore
    cost_efficiency: float = 0.0
    time_penalty: float = 0.0

    @property
    def adjusted_score(self) -> float:
        base = self.confidence.overall
        cost_factor = 1.0 - self.cost_efficiency * 0.2
        time_factor = 1.0 - self.time_penalty * 0.1
        return round(base * cost_factor * time_factor, 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "response": self.response.to_dict(),
            "confidence": self.confidence.to_dict(),
            "cost_efficiency": self.cost_efficiency,
            "time_penalty": self.time_penalty,
            "adjusted_score": self.adjusted_score,
        }


class EvaluationEngine:
    def __init__(self, confidence_scorer: Optional[ConfidenceScorer] = None, context: Optional[Dict[str, Any]] = None):
        self._scorer = confidence_scorer or ConfidenceScorer()
        self._context = context or {}

    def evaluate(self, response: ModelResponse, instruction: str = "") -> EvaluatedResponse:
        score = self._scorer.score(
            response=response.response_text,
            instruction=instruction,
            model_id=response.model_id,
            provider=response.provider,
        )
        cost_efficiency = self._compute_cost_efficiency(response)
        time_penalty = self._compute_time_penalty(response)
        evaluated = EvaluatedResponse(response=response, confidence=score, cost_efficiency=cost_efficiency, time_penalty=time_penalty)
        self._scorer.update_model_history(response.model_id, score.overall)
        return evaluated

    def evaluate_batch(self, responses: List[ModelResponse], instruction: str = "") -> List[EvaluatedResponse]:
        return [self.evaluate(r, instruction=instruction) for r in responses]

    async def evaluate_async(self, response: ModelResponse, instruction: str = "") -> EvaluatedResponse:
        return self.evaluate(response, instruction=instruction)

    async def evaluate_batch_async(self, responses: List[ModelResponse], instruction: str = "") -> List[EvaluatedResponse]:
        tasks = [self.evaluate_async(r, instruction=instruction) for r in responses]
        return await asyncio.gather(*tasks)

    def _compute_cost_efficiency(self, response: ModelResponse) -> float:
        if response.cost <= 0:
            return 0.0
        cost_per_char = response.cost / max(1, len(response.response_text))
        if cost_per_char < 0.001:
            return 0.1
        if cost_per_char < 0.01:
            return 0.3
        if cost_per_char < 0.1:
            return 0.5
        return min(1.0, cost_per_char * 10)

    def _compute_time_penalty(self, response: ModelResponse) -> float:
        if response.duration_ms <= 1000:
            return 0.0
        if response.duration_ms <= 5000:
            return 0.1
        if response.duration_ms <= 15000:
            return 0.3
        if response.duration_ms <= 30000:
            return 0.5
        return 0.8

    def pick_best(self, evaluated: List[EvaluatedResponse]) -> Optional[EvaluatedResponse]:
        if not evaluated:
            return None
        return max(evaluated, key=lambda e: e.adjusted_score)

    def rank(self, evaluated: List[EvaluatedResponse]) -> List[EvaluatedResponse]:
        return sorted(evaluated, key=lambda e: e.adjusted_score, reverse=True)

    def get_confidence_scorer(self) -> ConfidenceScorer:
        return self._scorer
