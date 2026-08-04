"""Shared intelligence result contracts.

This module provides the stable, versioned result types that cross the
boundaries between the intelligence engines. It intentionally does not contain
owners, prompts, secrets or unrestricted user data.

Where an existing production dataclass already exists (LanguageDecision,
InputUnderstandingResult, AmbiguityDecision), a Protocol is used to avoid
duplication and circular imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


class PrivacyClassification(str, Enum):
    PUBLIC = "public"
    OPERATIONAL = "operational"  # Needed to operate, not displayed to user.
    PRIVATE = "private"  # User-private, never transmitted or learned from.
    SECRET = "secret"  # Credentials, tokens; not stored in contracts.


class PersistencePolicy(str, Enum):
    EPHEMERAL = "ephemeral"  # Single request lifetime.
    SESSION = "session"
    CONVERSATION = "conversation"
    DURABLE = "durable"


class PipelineProfile(str, Enum):
    FAST_CONVERSATION = "fast_conversation"
    GOVERNED_ACTION = "governed_action"
    POST_EXECUTION_LEARNING = "post_execution_learning"
    BACKGROUND_MAINTENANCE = "background_maintenance"


class FailureMode(str, Enum):
    SAFE_DEFAULT = "safe_default"
    CLARIFICATION = "clarification"
    DENIAL = "denial"
    CORE_FALLBACK = "core_fallback"


@runtime_checkable
class LanguageDecision(Protocol):
    """Owner: Language engine (LanguageService)."""

    requested_language: Optional[str]
    conversation_language: str
    preferred_language: str
    detected_input_language: Optional[str]
    response_language: str
    decision_source: str
    confidence: float
    provider_language_support: bool
    fallback_required: bool
    reason: str


@runtime_checkable
class InputUnderstandingResult(Protocol):
    """Owner: Input Understanding engine (InputUnderstandingService)."""

    decision_id: str
    original_text: str
    normalized_text: str
    detected_languages: List[str]
    corrected_tokens: List[str]
    correction_confidence: float
    detected_entities: List[str]
    candidate_intents: List[str]
    selected_intent: str
    candidate_targets: List[str]
    selected_target: str
    ambiguity_type: str
    ambiguity_level: str
    confidence: float
    requires_clarification: bool
    clarification_reason: str
    risk_if_wrong: str
    assumptions: List[str]
    evidence_sources: List[str]


@runtime_checkable
class AmbiguityDecision(Protocol):
    """Owner: Ambiguity engine (InputUnderstandingService)."""

    id: str
    action: str
    auto_correct: bool
    infer: bool
    present_assumption: bool
    ask_clarification: bool
    reject: bool
    confidence: float
    selected_interpretation: str
    alternatives: List[str]
    risk_level: str
    reason: str


@dataclass
class IdentityResult:
    """Owner: Identity engine."""

    user_id: str = ""
    session_id: str = ""
    device_id: str = ""
    profile_id: str = ""
    trust_level: str = "local"
    permissions: List[str] = field(default_factory=list)
    schema_version: int = 1
    privacy: PrivacyClassification = PrivacyClassification.OPERATIONAL
    persistence: PersistencePolicy = PersistencePolicy.SESSION


@dataclass
class IntentResult:
    """Owner: Intent engine."""

    selected_intent: str = "conversation"
    candidate_intents: List[str] = field(default_factory=list)
    is_executable: bool = False
    is_informational: bool = True
    confidence: float = 0.0
    owner: str = "intent_engine"
    privacy: PrivacyClassification = PrivacyClassification.PUBLIC
    persistence: PersistencePolicy = PersistencePolicy.EPHEMERAL


@dataclass
class ContextSelection:
    """Owner: Context engine."""

    messages: List[Dict[str, str]] = field(default_factory=list)
    trimmed: int = 0
    summarized: bool = False
    total_tokens: int = 0
    included_memories: List[str] = field(default_factory=list)
    owner: str = "context_engine"
    privacy: PrivacyClassification = PrivacyClassification.PRIVATE
    persistence: PersistencePolicy = PersistencePolicy.EPHEMERAL


@dataclass
class MemorySelection:
    """Owner: Memory engine."""

    domains: List[str] = field(default_factory=list)
    facts: List[Dict[str, Any]] = field(default_factory=list)
    recency_cutoff: Optional[datetime] = None
    owner: str = "memory_engine"
    privacy: PrivacyClassification = PrivacyClassification.PRIVATE
    persistence: PersistencePolicy = PersistencePolicy.DURABLE


@dataclass
class WorldModelEvidence:
    """Owner: World Model engine. Evidence contract only in Phase II."""

    fact_id: str = ""
    subject: str = ""
    predicate: str = ""
    value: Any = None
    evidence_source: str = ""
    observed_at: str = ""
    confidence: float = 0.0
    freshness_seconds: int = 0
    privacy: PrivacyClassification = PrivacyClassification.OPERATIONAL
    user_correction_status: str = "unverified"
    owner: str = "world_model_engine"
    persistence: PersistencePolicy = PersistencePolicy.DURABLE


@dataclass
class PlanResult:
    """Owner: Planning engine."""

    plan_id: str = ""
    steps: List[Dict[str, Any]] = field(default_factory=list)
    is_conditional: bool = False
    is_parallel: bool = False
    can_cancel: bool = True
    can_recover: bool = False
    verification_required: bool = True
    owner: str = "planning_engine"
    privacy: PrivacyClassification = PrivacyClassification.OPERATIONAL
    persistence: PersistencePolicy = PersistencePolicy.SESSION


@dataclass
class ConfidenceSummary:
    """Owner: Confidence engine."""

    identity: float = 0.0
    language: float = 0.0
    input: float = 0.0
    intent: float = 0.0
    ambiguity: float = 0.0
    context: float = 0.0
    memory: float = 0.0
    world: float = 0.0
    plan: float = 0.0
    risk: float = 0.0
    governance: float = 0.0
    verification: float = 0.0
    overall: float = 0.0
    owner: str = "confidence_engine"
    privacy: PrivacyClassification = PrivacyClassification.OPERATIONAL
    persistence: PersistencePolicy = PersistencePolicy.EPHEMERAL


@dataclass
class RiskDecision:
    """Owner: Risk engine."""

    level: str = "low"  # low, medium, high, critical
    privacy_risk: bool = False
    security_risk: bool = False
    cost_risk: bool = False
    destructive: bool = False
    irreversible: bool = False
    uncertainty: float = 0.0
    requires_confirmation: bool = False
    owner: str = "risk_engine"
    privacy: PrivacyClassification = PrivacyClassification.OPERATIONAL
    persistence: PersistencePolicy = PersistencePolicy.EPHEMERAL


@dataclass
class GovernanceDecisionReference:
    """Owner: Governance engine."""

    decision: str = "allow"  # allow, confirm, deny
    reason_code: str = ""
    policy_id: str = ""
    authority_id: str = ""
    owner: str = "governance_engine"
    privacy: PrivacyClassification = PrivacyClassification.OPERATIONAL
    persistence: PersistencePolicy = PersistencePolicy.SESSION


@dataclass
class VerificationResult:
    """Owner: Verification engine."""

    expected: str = ""
    actual: Any = None
    verified: bool = False
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    failure_recovery: str = ""
    owner: str = "verification_engine"
    privacy: PrivacyClassification = PrivacyClassification.OPERATIONAL
    persistence: PersistencePolicy = PersistencePolicy.SESSION


@dataclass
class ExplanationResult:
    """Owner: Explanation engine."""

    reason_code: str = ""
    localized_summary: str = ""
    facts: Dict[str, Any] = field(default_factory=dict)
    language: str = "en"
    owner: str = "explanation_engine"
    privacy: PrivacyClassification = PrivacyClassification.PUBLIC
    persistence: PersistencePolicy = PersistencePolicy.EPHEMERAL

    def to_safe_dict(self) -> Dict[str, Any]:
        return {
            "reason_code": self.reason_code,
            "localized_summary": self.localized_summary,
            "facts": self.facts,
            "language": self.language,
        }


@dataclass
class LearningObservation:
    """Owner: Learning engine."""

    category: str = ""
    verified: bool = False
    fact_id: str = ""
    user_correction: Optional[str] = None
    outcome_success: Optional[bool] = None
    provider_performance: Optional[Dict[str, Any]] = None
    observed_at: str = ""
    owner: str = "learning_engine"
    privacy: PrivacyClassification = PrivacyClassification.PRIVATE
    persistence: PersistencePolicy = PersistencePolicy.DURABLE
