"""Sanitized divergence descriptions."""

from enum import Enum


class DivergenceSeverity(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


CRITICAL_CODES = frozenset(
    {
        "CORRELATION_MISMATCH",
        "EVIDENCE_HASH_MISMATCH",
        "ISSUER_MISMATCH",
        "CRITICAL_HEALTH",
    }
)
