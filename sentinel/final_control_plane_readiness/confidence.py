"""Final confidence normalization without authority semantics."""

from .signals import ConsolidatedSignalsV1


def consolidated_confidence(signals: ConsolidatedSignalsV1) -> float:
    trust = signals.trust_score or 0.0
    equivalence = signals.runtime_equivalence_rate * 100
    integrity = 100.0 if signals.evidence_integrity_valid else 0.0
    safety = 100.0 if signals.safety_healthy else 0.0
    return round(
        max(0.0, min(100.0, (trust + equivalence + integrity + safety) / 4)),
        2,
    )
