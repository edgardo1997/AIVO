"""Deterministic evaluation assembled from contract values."""

from sentinel.contracts import DecisionResultV1
from sentinel.shadow_decision_orchestrator import EquivalenceLevel

from .recommendation import RecommendationValue
from .risk import RiskLevel


class RecommendationEvaluationV1(DecisionResultV1):
    recommendation: RecommendationValue
    risk: RiskLevel
    confidence: float
    equivalence: EquivalenceLevel
    divergence_count: int
