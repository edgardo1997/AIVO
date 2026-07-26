"""Diagnostic-only comparison for controlled trial stages."""

from enum import Enum


class RuntimeTrialComparisonStatus(str, Enum):
    MATCH = "MATCH"
    EXPECTED_DIFFERENCE = "EXPECTED_DIFFERENCE"
    V2_WARNING = "V2_WARNING"
    CRITICAL_DIVERGENCE = "CRITICAL_DIVERGENCE"


class RuntimeTrialComparison:
    @staticmethod
    def compare(
        actual: dict[str, str],
        expected: dict[str, str] | None,
    ) -> RuntimeTrialComparisonStatus:
        if expected is None:
            return RuntimeTrialComparisonStatus.EXPECTED_DIFFERENCE
        missing = set(expected) - set(actual)
        if missing:
            return RuntimeTrialComparisonStatus.CRITICAL_DIVERGENCE
        differences = [key for key, value in expected.items() if actual[key] != value]
        if not differences:
            return RuntimeTrialComparisonStatus.MATCH
        if "authorization_hash" in differences or "policy_hash" in differences:
            return RuntimeTrialComparisonStatus.CRITICAL_DIVERGENCE
        return RuntimeTrialComparisonStatus.V2_WARNING
