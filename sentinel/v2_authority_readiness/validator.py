"""Final evidence evaluator using the central readiness contract."""

import hashlib
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from sentinel.contracts import ReadinessResultV1

from .control import V2AuthorityReadinessControl
from .gates import GateResult, ReadinessEvidenceV1, evaluate_all_gates
from .metrics import AuthorityReadinessMetrics
from .readiness import AuthorityReadinessState


class AuthorityReadinessResultV1(ReadinessResultV1):
    validation_id: str
    timestamp: datetime
    gates: tuple[GateResult, ...]
    risks: tuple[str, ...]
    recommendations: tuple[str, ...]

    @property
    def state(self) -> AuthorityReadinessState:
        """Temporary read-only compatibility for existing report consumers."""

        return self.status


class V2AuthorityReadinessEngine:
    def __init__(
        self,
        *,
        control: V2AuthorityReadinessControl,
        metrics: AuthorityReadinessMetrics | None = None,
    ) -> None:
        self.control = control
        self.metrics = metrics or AuthorityReadinessMetrics()

    def evaluate(
        self,
        evidence: ReadinessEvidenceV1,
    ) -> AuthorityReadinessResultV1 | None:
        if not self.control.enabled:
            return None
        gates = evaluate_all_gates(evidence)
        failed = tuple(gate for gate in gates if not gate.passed)
        if any(gate.blocking for gate in failed):
            state = AuthorityReadinessState.BLOCKED
        elif not failed:
            state = AuthorityReadinessState.HIGH_CONFIDENCE_REVIEW
        elif len(failed) == 1:
            state = AuthorityReadinessState.READY_FOR_HUMAN_REVIEW
        else:
            state = AuthorityReadinessState.INSUFFICIENT_EVIDENCE
        risks = tuple(code for gate in failed for code in gate.codes)
        recommendations = (
            ("CONSIDER_FUTURE_MIGRATION_REVIEW",)
            if state is AuthorityReadinessState.HIGH_CONFIDENCE_REVIEW
            else ("KEEP_LEGACY_AUTHORITY", "RESOLVE_FAILED_GATES")
        )
        self.metrics.record(state=state, gates=gates)
        validation_id = f"readiness_{uuid.uuid4().hex}"
        evidence_hash = _evidence_hash(evidence)
        return AuthorityReadinessResultV1(
            validation_id=validation_id,
            timestamp=datetime.now(timezone.utc),
            status=state,
            confidence=max(0.0, min(100.0, evidence.shadow_match_rate * 100)),
            evidence_hash=evidence_hash,
            correlation_id=validation_id,
            gates=gates,
            risks=risks,
            recommendations=recommendations,
        )


def _evidence_hash(evidence: ReadinessEvidenceV1) -> str:
    canonical = json.dumps(asdict(evidence), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
