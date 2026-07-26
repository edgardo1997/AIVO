"""Isolated observation of copied Legacy snapshots against passive V2."""

from copy import deepcopy
import hashlib
from time import perf_counter

from sentinel.contracts import (
    ConsentDecisionValueV1,
    EvidenceIntegrityStatusV1,
    HealthStateV1,
)
from sentinel.operational_telemetry_hub import OperationalEventV1
from sentinel.v2_unified_pipeline import (
    PassiveUnifiedPipelineV2,
    UnifiedPipelineRequestV1,
)

from .comparison import compare_legacy_to_v2
from .control import ShadowRuntimeRealControl
from .metrics import ShadowRuntimeMetrics, ShadowRuntimeMetricsSnapshotV1
from .models import (
    LegacyRuntimeSnapshotV1,
    ShadowRuntimeObservationResultV1,
)


class PassiveShadowRuntimeObserver:
    """Observes copies and cannot alter, block or replace Legacy results."""

    authority = False
    execution_requested = False

    def __init__(
        self,
        *,
        control: ShadowRuntimeRealControl,
        pipeline: PassiveUnifiedPipelineV2,
        metrics: ShadowRuntimeMetrics | None = None,
    ) -> None:
        self.control = control
        self.pipeline = pipeline
        self.metrics = metrics or ShadowRuntimeMetrics()

    def observe(
        self,
        *,
        legacy_snapshot: LegacyRuntimeSnapshotV1,
        pipeline_request: UnifiedPipelineRequestV1,
        consent_decision: ConsentDecisionValueV1 | None = None,
        human_actor: str | None = None,
    ) -> ShadowRuntimeObservationResultV1:
        started = perf_counter()
        snapshot_copy = LegacyRuntimeSnapshotV1.model_validate(deepcopy(legacy_snapshot.model_dump()))
        request_copy = UnifiedPipelineRequestV1.model_validate(deepcopy(pipeline_request.model_dump()))
        observation_id = _observation_id(snapshot_copy)
        if not self.control.enabled:
            result = ShadowRuntimeObservationResultV1(
                observation_id=observation_id,
                correlation_id=request_copy.correlation_id,
                evidence_hash=request_copy.evidence.payload_hash,
                timestamp=request_copy.timestamp,
                observed=False,
                warnings=("SHADOW_DISABLED",),
            )
            return result
        if snapshot_copy.correlation_id != request_copy.correlation_id:
            result = ShadowRuntimeObservationResultV1(
                observation_id=observation_id,
                correlation_id=request_copy.correlation_id,
                evidence_hash=request_copy.evidence.payload_hash,
                timestamp=request_copy.timestamp,
                observed=False,
                error_code="CORRELATION_MISMATCH",
            )
            self.metrics.record(
                latency_ms=(perf_counter() - started) * 1000,
                comparison=None,
                failed=True,
            )
            return result
        try:
            shadow = self.pipeline.evaluate(
                request_copy,
                consent_decision=consent_decision,
                human_actor=human_actor,
            )
            comparison = compare_legacy_to_v2(snapshot_copy, shadow)
            event = OperationalEventV1(
                event_id=f"telemetry:{observation_id}",
                correlation_id=shadow.correlation_id,
                evidence_hash=shadow.evidence_hash,
                issuer_id=shadow.issuer_id,
                timestamp=shadow.timestamp,
                event_type="V2_REAL_SHADOW_COMPARED",
                health_state=(HealthStateV1.DEGRADED if comparison.critical_count else HealthStateV1.OBSERVING),
                decision_state=(
                    "CRITICAL_DIVERGENCE"
                    if comparison.critical_count
                    else "MATCH"
                    if comparison.matched
                    else "DIVERGENCE"
                ),
                integrity_status=EvidenceIntegrityStatusV1.VERIFIED,
            )
            aggregator = self.pipeline.telemetry_hub.aggregator
            storage = self.pipeline.telemetry_hub.storage
            if aggregator is None or storage is None:
                raise RuntimeError("shared telemetry is unavailable")
            existing = storage.read_event(event.event_id)
            if existing is None:
                aggregator.ingest(event)
            elif existing != event:
                raise RuntimeError("shadow telemetry conflict")
            latency_ms = (perf_counter() - started) * 1000
            self.metrics.record(
                latency_ms=latency_ms,
                comparison=comparison,
                failed=False,
            )
            return ShadowRuntimeObservationResultV1(
                observation_id=observation_id,
                correlation_id=shadow.correlation_id,
                evidence_hash=shadow.evidence_hash,
                timestamp=shadow.timestamp,
                observed=True,
                pipeline_result=shadow,
                comparison=comparison,
            )
        except Exception as exc:
            self.metrics.record(
                latency_ms=(perf_counter() - started) * 1000,
                comparison=None,
                failed=True,
            )
            return ShadowRuntimeObservationResultV1(
                observation_id=observation_id,
                correlation_id=request_copy.correlation_id,
                evidence_hash=request_copy.evidence.payload_hash,
                timestamp=request_copy.timestamp,
                observed=False,
                error_code=_safe_error_code(exc),
            )

    def metrics_snapshot(self) -> ShadowRuntimeMetricsSnapshotV1:
        return self.metrics.snapshot()


def _observation_id(snapshot: LegacyRuntimeSnapshotV1) -> str:
    digest = hashlib.sha256(
        (f"{snapshot.snapshot_id}:{snapshot.correlation_id}:{snapshot.timestamp.isoformat()}").encode("utf-8")
    ).hexdigest()[:32]
    return f"shadow-observation:{digest}"


def _safe_error_code(exc: Exception) -> str:
    name = type(exc).__name__.upper()
    return "".join(character if character.isalnum() else "_" for character in name)[:64]
