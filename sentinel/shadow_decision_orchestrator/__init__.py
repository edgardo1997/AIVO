"""Passive Legacy/V2 decision comparison package."""

from .control import SHADOW_DECISION_ORCHESTRATOR_ENABLED, ShadowOrchestratorControl
from .equivalence import EquivalenceLevel
from .orchestrator import (
    ShadowContractSnapshotV1,
    ShadowDecisionOrchestrator,
    ShadowDecisionResultV1,
)

__all__ = [
    "SHADOW_DECISION_ORCHESTRATOR_ENABLED",
    "EquivalenceLevel",
    "ShadowContractSnapshotV1",
    "ShadowDecisionOrchestrator",
    "ShadowDecisionResultV1",
    "ShadowOrchestratorControl",
]
