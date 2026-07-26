"""Classification vocabulary for shadow decision differences."""

from enum import Enum


class DecisionClassification(str, Enum):
    EXPECTED_MATCH = "EXPECTED_MATCH"
    LEGACY_DIFFERENCE = "LEGACY_DIFFERENCE"
    V2_DIFFERENCE = "V2_DIFFERENCE"
    SECURITY_IMPROVEMENT = "SECURITY_IMPROVEMENT"
    CRITICAL_DIVERGENCE = "CRITICAL_DIVERGENCE"
