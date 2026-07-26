"""Deterministic classification of sanitized divergence codes."""

from dataclasses import dataclass
from enum import Enum


class DivergenceClassification(str, Enum):
    EXPECTED = "EXPECTED"
    LEGACY_BUG = "LEGACY_BUG"
    V2_BUG = "V2_BUG"
    SECURITY_IMPROVEMENT = "SECURITY_IMPROVEMENT"
    DATA_GAP = "DATA_GAP"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ClassifiedDivergence:
    code: str
    classification: DivergenceClassification
    critical: bool


def classify_divergence(
    code: str,
    *,
    context: tuple[str, ...] = (),
) -> ClassifiedDivergence:
    normalized = code.strip().lower()
    context_values = {value.strip().lower() for value in context}
    if normalized in {
        "missing_identity",
        "missing_policy_context",
        "missing_context",
        "missing_policy_version",
        "discovery_missing_evidence",
    }:
        return ClassifiedDivergence(
            code,
            DivergenceClassification.DATA_GAP,
            True,
        )
    if (
        normalized == "legacy_allow_v2_deny"
        and {
            "missing_policy_context",
            "missing_context",
        }
        & context_values
    ):
        return ClassifiedDivergence(
            code,
            DivergenceClassification.DATA_GAP,
            True,
        )
    if normalized.startswith("security_improvement"):
        return ClassifiedDivergence(
            code,
            DivergenceClassification.SECURITY_IMPROVEMENT,
            False,
        )
    if normalized.startswith("legacy_bug"):
        return ClassifiedDivergence(
            code,
            DivergenceClassification.LEGACY_BUG,
            False,
        )
    if normalized.startswith("v2_bug"):
        return ClassifiedDivergence(
            code,
            DivergenceClassification.V2_BUG,
            True,
        )
    if normalized.startswith("expected"):
        return ClassifiedDivergence(
            code,
            DivergenceClassification.EXPECTED,
            False,
        )
    if normalized.startswith(
        (
            "authorization_inconsistent",
            "replay_possible",
            "critical_",
        )
    ):
        return ClassifiedDivergence(
            code,
            DivergenceClassification.UNKNOWN,
            True,
        )
    return ClassifiedDivergence(
        code,
        DivergenceClassification.UNKNOWN,
        False,
    )
