"""IntelligenceCoordinator — orchestration without authority.

The coordinator chooses a pipeline profile, invokes existing owners (supplied by
callers), records stage timings and correlation, and stops early when the
outcome is already decided. It does NOT authorize, persist, route or execute.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from sentinel.intelligence.contracts import (
    AmbiguityDecision,
    ConfidenceSummary,
    FailureMode,
    GovernanceDecisionReference,
    InputUnderstandingResult,
    IntentResult,
    LanguageDecision,
    PipelineProfile,
    RiskDecision,
)
from sentinel.intelligence.pipeline_profiles import PipelineProfileDefinition, select_profile


@dataclass
class StageRecord:
    name: str
    owner: str
    started_at: float
    finished_at: float = 0.0
    skipped: bool = False
    stopped: bool = False
    reason: str = ""


@dataclass
class IntelligenceTrace:
    correlation_id: str
    profile: str
    stages: List[StageRecord] = field(default_factory=list)
    confidence: ConfidenceSummary = field(default_factory=ConfidenceSummary)
    governance: Optional[GovernanceDecisionReference] = None
    risk: Optional[RiskDecision] = None
    stopped: bool = False
    stop_reason: str = ""
    latency_ms: float = 0.0


class IntelligenceCoordinator:
    """Selects a profile and records a bounded, explainable trace.

    Authority remains with the existing owners: LanguageService,
    InputUnderstandingService, PolicyEngine, ToolExecutionGuard, etc.
    """

    def __init__(self):
        self._stages: Dict[str, Callable[[], Any]] = {}

    def register_stage(self, name: str, owner: str, fn: Callable[[], Any]) -> None:
        """Bind an existing owner to a stage name. The coordinator does not own the logic."""
        self._stages[name] = fn

    def coordinate(
        self,
        language: Optional[LanguageDecision] = None,
        understanding: Optional[InputUnderstandingResult] = None,
        ambiguity: Optional[AmbiguityDecision] = None,
        intent: Optional[IntentResult] = None,
        profile_override: Optional[PipelineProfile] = None,
    ) -> IntelligenceTrace:
        correlation_id = str(uuid.uuid4())
        start = time.monotonic()

        if profile_override is not None:
            # Use a string mapping; the enum value is the key.
            from sentinel.intelligence.pipeline_profiles import PROFILES
            profile = PROFILES.get(profile_override.value, PipelineProfileDefinition("fast_conversation"))
        else:
            is_executable = bool(intent and intent.is_executable)
            ambiguity_action = ambiguity.action if ambiguity else "proceed"
            profile = select_profile(
                intent=getattr(intent, "selected_intent", "conversation"),
                is_executable=is_executable,
                ambiguity_action=ambiguity_action,
            )

        trace = IntelligenceTrace(correlation_id=correlation_id, profile=profile.name)

        for stage in profile.required_stages:
            stage_start = time.monotonic()
            record = StageRecord(name=stage, owner=self._owner_for(stage), started_at=stage_start)

            # Stop early on unresolved ambiguity before planning/execution.
            if stage in ("planning", "risk_evaluation", "governance", "execution") and ambiguity and (ambiguity.ask_clarification or ambiguity.reject):
                record.stopped = True
                record.reason = "ambiguity_requires_resolution"
                record.finished_at = time.monotonic()
                trace.stages.append(record)
                trace.stopped = True
                trace.stop_reason = "ambiguity"
                break

            # Stop early on cancellation or governance denial if present.
            if trace.stop_reason:
                record.skipped = True
                record.finished_at = time.monotonic()
                trace.stages.append(record)
                continue

            fn = self._stages.get(stage)
            if fn is not None:
                try:
                    fn()
                except Exception as exc:
                    record.finished_at = time.monotonic()
                    trace.stages.append(record)
                    trace.stopped = True
                    trace.stop_reason = f"stage_failure:{stage}:{exc}"
                    break

            record.finished_at = time.monotonic()
            trace.stages.append(record)

        trace.latency_ms = (time.monotonic() - start) * 1000
        return trace

    @staticmethod
    def _owner_for(stage: str) -> str:
        owners = {
            "identity": "identity_engine",
            "language": "language_service",
            "input_understanding": "input_understanding_service",
            "intent": "intent_engine",
            "ambiguity": "input_understanding_service",
            "context_selection": "context_window",
            "memory_selection": "memory_engine",
            "world_model": "world_model_engine",
            "planning": "planner",
            "risk_evaluation": "risk_engine",
            "governance": "policy_engine",
            "execution": "tool_execution_guard",
            "verification": "execution_pipeline",
            "explanation": "explanation_service",
            "learning": "learning_engine",
            "persistence": "persistence_engine",
            "provider_routing": "model_router",
            "response_validation": "language_service",
        }
        return owners.get(stage, "unknown")
