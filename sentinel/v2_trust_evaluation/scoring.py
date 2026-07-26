"""Deterministic aggregate trust score."""

from dataclasses import dataclass

from .history import HistoricalEvidenceV1


@dataclass(frozen=True)
class TrustScore:
    value: float
    positive_factors: tuple[str, ...]
    negative_factors: tuple[str, ...]


class TrustScoringEngine:
    def calculate(self, evidence: HistoricalEvidenceV1) -> TrustScore:
        if evidence.window_count == 0:
            return TrustScore(0.0, (), ("INSUFFICIENT_HISTORY",))
        positive = []
        negative = []
        score = (
            evidence.stability_rate * 25
            + evidence.equivalence_rate * 30
            + evidence.integrity_rate * 25
            + evidence.healthy_window_rate * 20
        )
        if evidence.stability_rate >= 0.95:
            positive.append("STABILITY_HIGH")
        if evidence.equivalence_rate >= 0.99:
            positive.append("RUNTIME_EQUIVALENCE_HIGH")
        if evidence.integrity_rate >= 0.99:
            positive.append("EVIDENCE_INTEGRITY_HIGH")
        if evidence.healthy_window_rate >= 0.95:
            positive.append("HISTORICAL_HEALTH_HIGH")
        penalty = evidence.error_rate * 20
        penalty += evidence.divergence_rate * 20
        penalty += min(evidence.critical_divergences * 15, 45)
        penalty += min(evidence.incident_count * 2, 20)
        penalty += min(evidence.rollback_count * 5, 20)
        if evidence.error_rate:
            negative.append("ERRORS_OBSERVED")
        if evidence.divergence_rate:
            negative.append("DIVERGENCES_OBSERVED")
        if evidence.critical_divergences:
            negative.append("CRITICAL_DIVERGENCES")
        if evidence.incident_count:
            negative.append("INCIDENTS_OBSERVED")
        if evidence.rollback_count:
            negative.append("ROLLBACKS_OBSERVED")
        return TrustScore(
            value=max(0.0, min(100.0, score - penalty)),
            positive_factors=tuple(positive),
            negative_factors=tuple(negative),
        )
