"""Pure snapshot comparison with no runtime dependencies."""

from dataclasses import dataclass

from .equivalence import (
    EquivalenceClassification,
    RuntimeEquivalenceSnapshotV1,
)


@dataclass(frozen=True)
class EquivalenceComparison:
    classification: EquivalenceClassification
    differences: tuple[str, ...]
    compared_fields: int
    matching_fields: int
    timing_delta_ms: float


class RuntimeSnapshotComparator:
    def __init__(self, timing_tolerance_ms: float = 100.0) -> None:
        self.timing_tolerance_ms = max(0.0, timing_tolerance_ms)

    def compare(
        self,
        legacy: RuntimeEquivalenceSnapshotV1,
        v2: RuntimeEquivalenceSnapshotV1,
    ) -> EquivalenceComparison:
        fields = {
            "INTENT": legacy.intent_hash == v2.intent_hash,
            "EXECUTION_PLAN": (legacy.execution_plan_hash == v2.execution_plan_hash),
            "DISCOVERY": legacy.discovery_hash == v2.discovery_hash,
            "POLICY": legacy.policy_hash == v2.policy_hash,
            "AUTHORIZATION": (legacy.authorization_hash == v2.authorization_hash),
            "RUNTIME_STATUS": legacy.runtime_status == v2.runtime_status,
            "EXECUTION_RESULT": (legacy.execution_result == v2.execution_result),
            "TOOL_SELECTION": (legacy.tool_selection_hash == v2.tool_selection_hash),
            "EVENT_SEQUENCE": legacy.event_sequence == v2.event_sequence,
            "RETURN_CODE": legacy.return_code == v2.return_code,
        }
        differences = [name for name, matches in fields.items() if not matches]
        timing_delta = abs(legacy.execution_timing_ms - v2.execution_timing_ms)
        timing_differs = timing_delta > self.timing_tolerance_ms
        if not differences and not timing_differs:
            classification = EquivalenceClassification.EQUIVALENT
        elif any(name in differences for name in ("POLICY", "AUTHORIZATION", "TOOL_SELECTION")):
            classification = EquivalenceClassification.SECURITY_DIFFERENCE
        elif any(name in differences for name in ("EXECUTION_RESULT", "RETURN_CODE")):
            classification = EquivalenceClassification.UNEXPECTED_RESULT
        elif differences:
            classification = EquivalenceClassification.FUNCTIONAL_DIFFERENCE
        else:
            classification = EquivalenceClassification.TIMING_DIFFERENCE
        if timing_differs:
            differences.append("EXECUTION_TIMING")
        return EquivalenceComparison(
            classification=classification,
            differences=tuple(differences),
            compared_fields=len(fields) + 1,
            matching_fields=sum(fields.values()) + int(not timing_differs),
            timing_delta_ms=timing_delta,
        )
