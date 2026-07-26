"""Deterministic equivalence vocabulary."""

from enum import Enum


class EquivalenceLevel(str, Enum):
    MATCH = "MATCH"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    DIVERGENCE = "DIVERGENCE"
    CRITICAL_DIVERGENCE = "CRITICAL_DIVERGENCE"
