"""Final signal aggregator with no runtime or activation capability."""

import hashlib
import json

from .confidence import consolidated_confidence
from .control import FinalControlPlaneControl
from .decision import FinalReadinessDecision, FinalReadinessStatus
from .gates import evaluate_gates
from .metrics import FinalReadinessMetrics
from .signals import ConsolidatedSignalsV1


class FinalControlPlaneAggregator:
    def __init__(
        self,
        *,
        control: FinalControlPlaneControl,
        metrics: FinalReadinessMetrics | None = None,
    ) -> None:
        self.control = control
        self.metrics = metrics or FinalReadinessMetrics()

    def evaluate(
        self,
        signals: ConsolidatedSignalsV1,
    ) -> FinalReadinessDecision | None:
        if not self.control.enabled:
            return None
        gates = evaluate_gates(signals)
        failed = tuple(gate for gate in gates if not gate.passed)
        passed_ids = tuple(gate.gate_id for gate in gates if gate.passed)
        failed_ids = tuple(gate.gate_id for gate in failed)
        warnings = tuple(code for gate in failed for code in gate.codes)
        confidence = consolidated_confidence(signals)
        if any(gate.blocking for gate in failed):
            status = FinalReadinessStatus.BLOCKED
        elif not signals.evidence_available or signals.trust_score is None:
            status = FinalReadinessStatus.INSUFFICIENT_EVIDENCE
        elif signals.authority_readiness_status in {"BLOCKED", "NOT_READY"}:
            status = FinalReadinessStatus.NOT_APPROVED
        elif failed:
            status = FinalReadinessStatus.INSUFFICIENT_EVIDENCE
        elif signals.trust_confidence == "TRUST_READY_REVIEW" and confidence >= 90:
            status = FinalReadinessStatus.HIGH_CONFIDENCE_REVIEW
        else:
            status = FinalReadinessStatus.READY_FOR_HUMAN_REVIEW
        self.metrics.record(status=status, failed_gates=len(failed))
        evidence_hash = _evidence_hash(signals)
        return FinalReadinessDecision(
            status=status,
            confidence=confidence,
            passed_gates=passed_ids,
            failed_gates=failed_ids,
            warnings=warnings,
            evidence_hash=evidence_hash,
            correlation_id=f"final-readiness:{evidence_hash[:24]}",
        )


def _evidence_hash(signals: ConsolidatedSignalsV1) -> str:
    canonical = json.dumps(
        signals.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
