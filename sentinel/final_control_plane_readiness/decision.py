"""Final readiness specialization of the central readiness contract."""

from sentinel.contracts import ReadinessResultV1, ReadinessStateValueV1

FinalReadinessStatus = ReadinessStateValueV1


class FinalReadinessDecision(ReadinessResultV1):
    passed_gates: tuple[str, ...]
    failed_gates: tuple[str, ...]
    warnings: tuple[str, ...]
