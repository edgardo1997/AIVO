"""In-memory contract history converted to existing trust evidence."""

from sentinel.contracts import EvidenceIntegrityStatusV1, HealthStateV1
from sentinel.v2_trust_evaluation import HistoricalEvidenceV1

from .comparison import ShadowComparisonV1
from .equivalence import EquivalenceLevel


class ShadowContractHistory:
    def __init__(self) -> None:
        self._entries: list[tuple[ShadowComparisonV1, EvidenceIntegrityStatusV1, HealthStateV1]] = []

    def append(
        self,
        comparison: ShadowComparisonV1,
        *,
        integrity: EvidenceIntegrityStatusV1,
        health: HealthStateV1,
    ) -> None:
        self._entries.append((comparison, integrity, health))

    def trust_evidence(self) -> HistoricalEvidenceV1:
        total = len(self._entries)
        matches = sum(comparison.classification is EquivalenceLevel.MATCH for comparison, _, _ in self._entries)
        divergences = sum(
            comparison.classification
            in {
                EquivalenceLevel.DIVERGENCE,
                EquivalenceLevel.CRITICAL_DIVERGENCE,
            }
            for comparison, _, _ in self._entries
        )
        critical = sum(
            comparison.classification is EquivalenceLevel.CRITICAL_DIVERGENCE for comparison, _, _ in self._entries
        )
        verified = sum(integrity is EvidenceIntegrityStatusV1.VERIFIED for _, integrity, _ in self._entries)
        healthy = sum(health is HealthStateV1.HEALTHY for _, _, health in self._entries)
        return HistoricalEvidenceV1(
            window_count=total,
            total_events=total,
            stable_windows=matches,
            equivalence_rate=matches / max(total, 1),
            integrity_rate=verified / max(total, 1),
            healthy_window_rate=healthy / max(total, 1),
            error_rate=0.0,
            divergence_rate=divergences / max(total, 1),
            critical_divergences=critical,
            incident_count=0,
            rollback_count=0,
        )

    def __len__(self) -> int:
        return len(self._entries)
