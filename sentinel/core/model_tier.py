"""Model tier routing.

Request-aware selection of model capability tiers.  The tier mechanism is
provider-independent: it derives tiers from existing model capability metadata
and user request characteristics instead of hardcoding provider or model names.
"""

from __future__ import annotations
import dataclasses
from dataclasses import dataclass, field
from enum import Enum, IntEnum
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sentinel.core.context_budget import RequestPurpose
from sentinel.core.router_types import ProviderSpec, TaskType
from sentinel.models import ModelMetadata

logger = __import__("logging").getLogger(__name__)


class ModelTier(IntEnum):
    """Logical capability tiers, lowest to highest."""

    DETERMINISTIC = 0
    FAST_CONVERSATIONAL = 1
    BALANCED_REASONING = 2
    ADVANCED_REASONING = 3
    MULTI_MODEL_COORDINATION = 4


class ExecutionMode(str, Enum):
    """Execution path chosen for the request."""

    DETERMINISTIC = "deterministic"
    LLM = "llm"
    DEFERRED = "deferred"


class RiskLevel(str, Enum):
    """Risk classification for the request."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class LatencyClass(str, Enum):
    """Broad latency expectation for reporting."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CostClass(str, Enum):
    """Broad cost expectation for reporting."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class RequestProfile:
    """Inputs used to decide the appropriate tier."""

    text: str = ""
    purpose: RequestPurpose = RequestPurpose.CONVERSATION
    task_type: Optional[TaskType] = None
    history_length: int = 0
    num_tools: int = 0
    has_action: bool = False
    action_name: Optional[str] = None
    known_command: bool = False
    deterministic: bool = False
    destructive: bool = False
    governed: bool = False
    risk_level: RiskLevel = RiskLevel.LOW
    privacy_local_only: bool = False
    cloud_allowed: bool = True
    budget_remaining_usd: Optional[float] = None
    user_preferred_tier: Optional[ModelTier] = None
    user_quality_cost_preference: str = "balanced"  # "fast", "balanced", "quality"
    estimated_tokens: int = 0
    preferred_provider: Optional[str] = None
    preferred_model: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "purpose": self.purpose.value,
            "task_type": self.task_type.value if self.task_type else None,
            "history_length": self.history_length,
            "num_tools": self.num_tools,
            "has_action": self.has_action,
            "action_name": self.action_name,
            "known_command": self.known_command,
            "deterministic": self.deterministic,
            "destructive": self.destructive,
            "governed": self.governed,
            "risk_level": self.risk_level.value,
            "privacy_local_only": self.privacy_local_only,
            "cloud_allowed": self.cloud_allowed,
            "budget_remaining_usd": self.budget_remaining_usd,
            "user_preferred_tier": self.user_preferred_tier.value if self.user_preferred_tier is not None else None,
            "user_quality_cost_preference": self.user_quality_cost_preference,
            "estimated_tokens": self.estimated_tokens,
            "preferred_provider": self.preferred_provider,
            "preferred_model": self.preferred_model,
        }


@dataclass
class ModelTierDecision:
    """Authoritative tier decision consumed by ProviderSelector.

    Owner: sentinel.core.model_tier.ModelTierSelector
    Producer: ModelTierSelector.select_tier
    Consumers: ProviderSelector, AIService, telemetry
    Persistence: recorded in selection_trace; no sensitive details exposed
    Security classification: operational metadata only
    Failure behavior: graceful degradation with downgrade truthfully recorded
    """

    requested_tier: ModelTier
    selected_tier: ModelTier
    minimum_required_tier: ModelTier
    maximum_allowed_tier: ModelTier
    reason_codes: List[str] = field(default_factory=list)
    confidence: float = 0.0
    escalation_required: bool = False
    downgrade_applied: bool = False
    downgrade_reason: Optional[str] = None
    eligible_models: List[str] = field(default_factory=list)
    excluded_models: List[str] = field(default_factory=list)
    fallback_tier: Optional[ModelTier] = None
    user_override: bool = False
    risk_level: RiskLevel = RiskLevel.LOW
    context_requirement: int = 4096
    estimated_latency_class: LatencyClass = LatencyClass.LOW
    estimated_cost_class: CostClass = CostClass.LOW
    execution_mode: ExecutionMode = ExecutionMode.LLM

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requested_tier": self.requested_tier.value,
            "selected_tier": self.selected_tier.value,
            "minimum_required_tier": self.minimum_required_tier.value,
            "maximum_allowed_tier": self.maximum_allowed_tier.value,
            "reason_codes": list(self.reason_codes),
            "confidence": round(self.confidence, 3),
            "escalation_required": self.escalation_required,
            "downgrade_applied": self.downgrade_applied,
            "downgrade_reason": self.downgrade_reason,
            "eligible_models": list(self.eligible_models),
            "excluded_models": list(self.excluded_models),
            "fallback_tier": self.fallback_tier.value if self.fallback_tier is not None else None,
            "user_override": self.user_override,
            "risk_level": self.risk_level.value,
            "context_requirement": self.context_requirement,
            "estimated_latency_class": self.estimated_latency_class.value,
            "estimated_cost_class": self.estimated_cost_class.value,
            "execution_mode": self.execution_mode.value,
        }


# Heuristic keyword sets.  These classify the *request*, not the model.
_DETERMINISTIC_ACTIONS = {
    "open", "launch", "start", "close", "quit", "play", "pause", "stop",
    "status", "confirm", "cancel", "yes", "no",
}
_TIER_1_KEYWORDS = {
    "hello", "hi", "greet", "rewrit", "translat", "explain briefly",
    "what is", "who is", "how are", "simple", "short", "quick",
}
_TIER_2_KEYWORDS = {
    "debug", "code", "python", "programming", "technical", "plan", "steps",
    "implement", "function", "refactor", "tool", "select", "moderate",
    "multi-step", "limited ambiguity",
}
_TIER_3_KEYWORDS = {
    "architecture", "security", "complex", "ambiguous", "review", "analyse",
    "analyze", "consequential", "difficult", "high-precision", "root cause",
    "vulnerability", "threat model", "design",
}
_TIER_4_QUALIFIERS = {
    "multi model", "independent review", "council", "ensemble", "safety-critical",
    "high value", "architectural review", "security audit",
}


def _contains_any(text: str, tokens: set) -> bool:
    lowered = text.lower()
    for token in tokens:
        if token in lowered:
            return True
    return False


def _count_matches(text: str, tokens: set) -> int:
    lowered = text.lower()
    return sum(1 for token in tokens if token in lowered)


def request_risk_level(profile: RequestProfile) -> RiskLevel:
    """Combine explicit risk flags with text-derived risk."""
    if profile.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        return profile.risk_level
    if profile.destructive or profile.governed:
        return RiskLevel.HIGH
    txt = profile.text
    if _contains_any(txt, {"security", "vulnerability", "threat", "consequential", "critical"}):
        return RiskLevel.HIGH
    if _contains_any(txt, {"debug", "plan", "multi-step", "ambiguous"}):
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def classify_request_minimum_tier(profile: RequestProfile) -> Tuple[ModelTier, List[str]]:
    """Return the minimum tier required to satisfy the request safely."""
    reasons: List[str] = []
    text = profile.text or ""

    # Tier 0: deterministic, non-destructive, non-governed actions
    if (
        profile.deterministic
        or profile.known_command
        or (profile.action_name and not profile.governed and not profile.destructive)
    ):
        if _contains_any(text, _DETERMINISTIC_ACTIONS):
            reasons.append("known_deterministic_action")
            return ModelTier.DETERMINISTIC, reasons

    # Start from purpose baseline
    purpose = profile.purpose
    if purpose == RequestPurpose.CONVERSATION:
        tier = ModelTier.FAST_CONVERSATIONAL
        reasons.append("purpose_conversation")
    elif purpose == RequestPurpose.TECHNICAL:
        tier = ModelTier.BALANCED_REASONING
        reasons.append("purpose_technical")
    elif purpose == RequestPurpose.REASONING:
        tier = ModelTier.ADVANCED_REASONING
        reasons.append("purpose_reasoning")
    elif purpose == RequestPurpose.GOVERNED_ACTION:
        tier = ModelTier.BALANCED_REASONING
        reasons.append("purpose_governed_action")
    else:
        tier = ModelTier.FAST_CONVERSATIONAL
        reasons.append("default_conversation")

    # Keyword-based adjustments
    t1_hits = _count_matches(text, _TIER_1_KEYWORDS)
    t2_hits = _count_matches(text, _TIER_2_KEYWORDS)
    t3_hits = _count_matches(text, _TIER_3_KEYWORDS)
    t4_hits = _count_matches(text, _TIER_4_QUALIFIERS)

    if t4_hits:
        tier = max(tier, ModelTier.MULTI_MODEL_COORDINATION)
        reasons.append("tier_4_qualifier")
    elif t3_hits:
        tier = max(tier, ModelTier.ADVANCED_REASONING)
        reasons.append("advanced_reasoning_signal")
    elif t2_hits:
        tier = max(tier, ModelTier.BALANCED_REASONING)
        reasons.append("balanced_reasoning_signal")
    elif t1_hits and tier < ModelTier.FAST_CONVERSATIONAL:
        tier = max(tier, ModelTier.FAST_CONVERSATIONAL)
        reasons.append("fast_conversational_signal")

    # Risk escalation
    risk = request_risk_level(profile)
    if risk == RiskLevel.HIGH and tier < ModelTier.BALANCED_REASONING:
        tier = ModelTier.BALANCED_REASONING
        reasons.append("high_risk_escalation")
    if risk == RiskLevel.CRITICAL and tier < ModelTier.ADVANCED_REASONING:
        tier = ModelTier.ADVANCED_REASONING
        reasons.append("critical_risk_escalation")

    # Tool use
    if profile.num_tools > 0 and not profile.governed and tier < ModelTier.BALANCED_REASONING:
        tier = max(tier, ModelTier.BALANCED_REASONING)
        reasons.append("tool_use")

    # Context size
    if profile.estimated_tokens > 8000 and tier < ModelTier.BALANCED_REASONING:
        tier = max(tier, ModelTier.BALANCED_REASONING)
        reasons.append("large_context")
    if profile.estimated_tokens > 32000 and tier < ModelTier.ADVANCED_REASONING:
        tier = max(tier, ModelTier.ADVANCED_REASONING)
        reasons.append("very_large_context")

    # User preference floor
    if profile.user_preferred_tier is not None and tier < profile.user_preferred_tier:
        tier = profile.user_preferred_tier
        reasons.append("user_preferred_floor")

    return tier, reasons


def tier_for_model(model: ModelMetadata) -> ModelTier:
    """Derive a tier for a model using existing capability metadata."""
    if not model:
        return ModelTier.FAST_CONVERSATIONAL

    # Multi-model coordination is never assigned automatically.
    if model.supports_reasoning and model.context_window >= 32000:
        return ModelTier.ADVANCED_REASONING
    if (
        model.supports_reasoning
        or model.supports_coding
        or model.supports_tool_calling
        or model.context_window >= 16000
    ):
        return ModelTier.BALANCED_REASONING
    return ModelTier.FAST_CONVERSATIONAL


def tier_for_provider(provider: ProviderSpec) -> ModelTier:
    """Estimate the tier a provider can satisfy from its task types."""
    if not provider:
        return ModelTier.FAST_CONVERSATIONAL

    # Task types already encode capability intent.
    task_values = {t.value for t in provider.task_types}
    if TaskType.REASONING.value in task_values or TaskType.ANALYSIS.value in task_values:
        if provider.is_local:
            return ModelTier.BALANCED_REASONING
        return ModelTier.ADVANCED_REASONING
    if TaskType.CODE.value in task_values:
        if provider.is_local:
            return ModelTier.BALANCED_REASONING
        return ModelTier.ADVANCED_REASONING
    if TaskType.QUICK.value in task_values and not {TaskType.REASONING.value, TaskType.ANALYSIS.value, TaskType.CODE.value} & task_values:
        return ModelTier.FAST_CONVERSATIONAL
    if TaskType.LOCAL.value in task_values and not {TaskType.REASONING.value, TaskType.ANALYSIS.value, TaskType.CODE.value} & task_values:
        return ModelTier.FAST_CONVERSATIONAL
    return ModelTier.BALANCED_REASONING


def _model_cost_class(cost: float) -> CostClass:
    if cost <= 0.0:
        return CostClass.LOW
    if cost <= 0.005:
        return CostClass.LOW
    if cost <= 0.05:
        return CostClass.MEDIUM
    return CostClass.HIGH


def _model_latency_class(is_local: bool, cost: float) -> LatencyClass:
    if is_local:
        return LatencyClass.LOW
    if cost <= 0.005:
        return LatencyClass.LOW
    if cost <= 0.05:
        return LatencyClass.MEDIUM
    return LatencyClass.HIGH


def _max_allowed_tier(profile: RequestProfile, available_tiers: List[ModelTier]) -> ModelTier:
    """Compute the maximum tier that constraints allow."""
    # Privacy ceiling
    ceiling = ModelTier.MULTI_MODEL_COORDINATION
    reasons = []
    if profile.privacy_local_only or profile.cloud_allowed is False:
        ceiling = ModelTier.BALANCED_REASONING
        reasons.append("privacy_ceiling")

    # Budget ceiling
    if profile.budget_remaining_usd is not None and profile.budget_remaining_usd <= 0.0:
        ceiling = ModelTier.FAST_CONVERSATIONAL
        reasons.append("budget_depleted")
    elif profile.budget_remaining_usd is not None and profile.budget_remaining_usd < 0.5:
        ceiling = ModelTier.BALANCED_REASONING
        reasons.append("budget_constraint")

    # User quality/cost preference cannot exceed hard constraints
    pref = profile.user_quality_cost_preference
    if pref == "fast":
        ceiling = min(ceiling, ModelTier.BALANCED_REASONING)
        reasons.append("user_pref_fast")
    elif pref == "quality":
        reasons.append("user_pref_quality")

    # User explicit tier ceiling
    if profile.user_preferred_tier is not None:
        if not profile.user_override:
            ceiling = min(ceiling, profile.user_preferred_tier)
            reasons.append("user_preferred_ceiling")

    # Multi-model is never selected unless explicitly requested
    if ceiling == ModelTier.MULTI_MODEL_COORDINATION and not _contains_any(
        profile.text, _TIER_4_QUALIFIERS | {"explicit multi model"}
    ):
        ceiling = ModelTier.ADVANCED_REASONING
        reasons.append("tier_4_not_auto")

    return ceiling


class ModelTierSelector:
    """Authoritative producer of ModelTierDecision objects."""

    def __init__(self, registry: Optional[Any] = None):
        self._registry = registry

    def _resolve_provider_model_tier(self, provider: ProviderSpec) -> ModelTier:
        if self._registry is not None:
            try:
                model = self._registry.get(provider.default_model)
                if model:
                    return tier_for_model(model)
            except Exception:
                pass
        return tier_for_provider(provider)

    def _resolve_model_tier(self, model: ModelMetadata) -> ModelTier:
        return tier_for_model(model)

    def select_tier(
        self,
        profile: RequestProfile,
        models: Sequence[ModelMetadata],
    ) -> ModelTierDecision:
        """Classify the request and produce a tier decision."""
        minimum, reasons = classify_request_minimum_tier(profile)

        # Multi-model only allowed when explicitly signalled
        if minimum == ModelTier.MULTI_MODEL_COORDINATION and not _contains_any(profile.text, _TIER_4_QUALIFIERS):
            minimum = ModelTier.ADVANCED_REASONING
            reasons.append("tier_4_requires_explicit_signal")

        # Deterministic path
        if minimum == ModelTier.DETERMINISTIC:
            if not profile.governed and not profile.destructive:
                return ModelTierDecision(
                    requested_tier=ModelTier.DETERMINISTIC,
                    selected_tier=ModelTier.DETERMINISTIC,
                    minimum_required_tier=ModelTier.DETERMINISTIC,
                    maximum_allowed_tier=ModelTier.DETERMINISTIC,
                    reason_codes=reasons,
                    confidence=0.95,
                    risk_level=request_risk_level(profile),
                    execution_mode=ExecutionMode.DETERMINISTIC,
                    eligible_models=[],
                    estimated_latency_class=LatencyClass.LOW,
                    estimated_cost_class=CostClass.LOW,
                )
            # Governed/destructive deterministic actions are not auto-executed
            reasons.append("governed_deterministic_requires_llm_review")
            minimum = ModelTier.BALANCED_REASONING

        available_tiers = sorted({tier_for_model(m) for m in models}, reverse=True)
        maximum = _max_allowed_tier(profile, available_tiers) if available_tiers else minimum

        # If hard constraints make the required tier impossible, record that escalation is needed
        escalation = minimum > maximum
        if escalation:
            reasons.append("minimum_tier_exceeds_maximum_constraints")

        # Preferred tier starts at minimum and is raised by quality preference or high value
        preferred = minimum
        if profile.user_quality_cost_preference == "quality" and preferred < ModelTier.ADVANCED_REASONING:
            preferred = min(ModelTier.ADVANCED_REASONING, maximum)
            reasons.append("quality_preference")
        if request_risk_level(profile) == RiskLevel.HIGH and preferred < ModelTier.ADVANCED_REASONING:
            preferred = min(ModelTier.ADVANCED_REASONING, maximum)
            reasons.append("risk_preferred_tier")

        # Filter eligible by minimum capability and context window
        eligible: List[str] = []
        excluded: List[str] = []
        for m in models:
            mt = tier_for_model(m)
            if mt < minimum:
                excluded.append(m.id)
                continue
            if m.context_window < profile.estimated_tokens:
                excluded.append(m.id)
                continue
            eligible.append(m.id)

        # Escalation/downgrade resolution
        selected = preferred
        downgrade_applied = False
        downgrade_reason: Optional[str] = None
        fallback_tier: Optional[ModelTier] = None

        # Try preferred -> maximum, then minimum -> fallback
        if eligible:
            eligible_tiers = sorted({tier_for_model(m) for m in models if m.id in eligible}, reverse=True)
            if preferred in eligible_tiers and preferred <= maximum:
                selected = preferred
            elif maximum in eligible_tiers and maximum >= minimum:
                selected = min(maximum, preferred)
                downgrade_applied = preferred > maximum
                if downgrade_applied:
                    downgrade_reason = "cost_privacy_or_preference_ceiling"
                    fallback_tier = selected
            else:
                # Find the highest eligible tier that is still >= minimum
                candidates = [t for t in eligible_tiers if t >= minimum and t <= maximum]
                if candidates:
                    selected = max(candidates)
                    if selected != preferred:
                        downgrade_applied = True
                        downgrade_reason = "preferred_tier_unavailable"
                        fallback_tier = selected
                else:
                    # No candidate meets the minimum: record degraded fallback
                    best_available = max(eligible_tiers) if eligible_tiers else ModelTier.FAST_CONVERSATIONAL
                    selected = best_available
                    downgrade_applied = True
                    downgrade_reason = "no_eligible_model_meets_minimum"
                    fallback_tier = best_available
        else:
            # No models at all
            selected = minimum
            downgrade_applied = True
            downgrade_reason = "no_models_available"
            fallback_tier = minimum

        if selected > maximum:
            selected = maximum
            escalation = True
            reasons.append("escalation_ceiling_applied")

        # Latency/cost classes from the selected tier
        latency = LatencyClass.LOW
        cost = CostClass.LOW
        for m in models:
            if m.id in eligible and tier_for_model(m) == selected:
                latency = _model_latency_class(m.local, m.cost)
                cost = _model_cost_class(m.cost)
                break
        if not eligible:
            latency = LatencyClass.HIGH
            cost = CostClass.HIGH

        user_override = (
            profile.user_preferred_tier is not None
            and profile.user_preferred_tier >= minimum
            and profile.user_preferred_tier <= maximum
        )

        return ModelTierDecision(
            requested_tier=preferred,
            selected_tier=selected,
            minimum_required_tier=minimum,
            maximum_allowed_tier=maximum,
            reason_codes=reasons,
            confidence=0.8 if not downgrade_applied and not escalation else 0.6,
            escalation_required=escalation,
            downgrade_applied=downgrade_applied,
            downgrade_reason=downgrade_reason,
            eligible_models=eligible,
            excluded_models=excluded,
            fallback_tier=fallback_tier,
            user_override=user_override,
            risk_level=request_risk_level(profile),
            context_requirement=max(profile.estimated_tokens, 4096),
            estimated_latency_class=latency,
            estimated_cost_class=cost,
            execution_mode=ExecutionMode.LLM,
        )
