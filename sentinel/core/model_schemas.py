"""Canonical contracts for model inference and provider routing."""

from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CapabilityStatus(str, Enum):
    VERIFIED = "verified"
    DECLARED = "declared"
    PROBED = "probed"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


class ModelCapability(BaseModel):
    name: str = Field(..., description="Canonical capability name")
    status: CapabilityStatus = CapabilityStatus.UNKNOWN
    source: str = "declared"  # declared, probed, verified, unknown

    model_config = ConfigDict(extra="forbid")


class FallbackPolicy(str, Enum):
    NONE = "none"
    SAME_PROVIDER = "same_provider"
    LOCAL_ONLY = "local_only"
    AUTHORIZED_CLOUD = "authorized_cloud"
    ORDERED_CHAIN = "ordered_chain"


class PrivacyRequirement(str, Enum):
    LOCAL_ONLY = "local_only"
    LOCAL_PREFERRED = "local_preferred"
    CLOUD_ALLOWED = "cloud_allowed"


class ModelRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: "")
    correlation_id: str = Field(default_factory=lambda: "")
    user_id: str = Field(default_factory=lambda: "")
    session_id: str = Field(default_factory=lambda: "")
    task_type: str = "chat"
    required_capabilities: List[str] = Field(default_factory=list)
    preferred_capabilities: List[str] = Field(default_factory=list)
    privacy_requirement: PrivacyRequirement = PrivacyRequirement.LOCAL_PREFERRED
    local_only: bool = False
    cloud_allowed: bool = False
    cloud_authority_reference: str = ""
    max_cost: Optional[float] = None
    max_latency_ms: Optional[int] = None
    context_tokens: int = 0
    reserved_output_tokens: int = 512
    streaming_required: bool = False
    tool_calling_required: bool = False
    structured_output_required: bool = False
    vision_required: bool = False
    provider_preference: Optional[str] = None
    model_preference: Optional[str] = None
    fallback_policy: FallbackPolicy = FallbackPolicy.NONE

    @model_validator(mode="after")
    def enforce_privacy(self):
        if self.privacy_requirement == PrivacyRequirement.LOCAL_ONLY:
            self.local_only = True
            self.cloud_allowed = False
        return self

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class SelectionReasonCode(str, Enum):
    LOCAL_CAPABLE_PREFERRED = "LOCAL_CAPABLE_PREFERRED"
    LOCAL_REQUIRED = "LOCAL_REQUIRED"
    CLOUD_AUTHORIZED_LOCAL_INSUFFICIENT = "CLOUD_AUTHORIZED_LOCAL_INSUFFICIENT"
    USER_PROVIDER_PREFERENCE_ALLOWED = "USER_PROVIDER_PREFERENCE_ALLOWED"
    LOWEST_ESTIMATED_COST = "LOWEST_ESTIMATED_COST"
    LOWEST_ESTIMATED_LATENCY = "LOWEST_ESTIMATED_LATENCY"
    NO_ELIGIBLE_MODEL = "NO_ELIGIBLE_MODEL"
    CLOUD_NOT_AUTHORIZED = "CLOUD_NOT_AUTHORIZED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    CAPABILITY_MISMATCH = "CAPABILITY_MISMATCH"
    UNKNOWN_CAPABILITY = "UNKNOWN_CAPABILITY"
    PROVIDER_UNHEALTHY = "PROVIDER_UNHEALTHY"
    PROVIDER_DISABLED = "PROVIDER_DISABLED"


class ModelCandidate(BaseModel):
    provider_id: str
    model_id: str
    model_name: str = ""
    capabilities: List[ModelCapability] = Field(default_factory=list)
    is_local: bool = False
    is_cloud: bool = True
    estimated_cost: float = 0.0
    estimated_latency_ms: int = 0
    context_window: int = 0
    healthy: bool = True
    disabled: bool = False
    reason_excluded: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class RoutingDecision(BaseModel):
    selected_provider: str = ""
    selected_model: str = ""
    selection_reason_code: SelectionReasonCode = SelectionReasonCode.NO_ELIGIBLE_MODEL
    candidate_count: int = 0
    matched_capabilities: List[str] = Field(default_factory=list)
    missing_capabilities: List[str] = Field(default_factory=list)
    cloud_used: bool = False
    authority_reference: str = ""
    estimated_cost: float = 0.0
    estimated_latency_ms: int = 0
    fallback_chain: List[str] = Field(default_factory=list)
    confidence: str = "high"  # high, medium, low
    candidates: List[ModelCandidate] = Field(default_factory=list)
    safe_explanation: str = ""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class InferenceResult(BaseModel):
    provider: str
    model: str
    response: str = ""
    tool_calls: List[dict] = Field(default_factory=list)
    usage: dict = Field(default_factory=dict)
    decision: Optional[RoutingDecision] = None
    correlation_id: str = ""

    model_config = ConfigDict(extra="forbid")


class UsageRecord(BaseModel):
    request_id: str
    correlation_id: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    actual_cost: float = 0.0
    latency_ms: float = 0.0
    routing_reason: str = ""
    fallback: bool = False
    status: str = "ok"

    model_config = ConfigDict(extra="forbid")


class ProviderState(str, Enum):
    NOT_INSTALLED = "not_installed"
    STOPPED = "stopped"
    STARTING = "starting"
    LOADING_MODEL = "loading_model"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    DISABLED = "disabled"


class ModelState(BaseModel):
    provider_id: str
    model_id: str
    state: ProviderState = ProviderState.STOPPED
    configured: bool = False
    authenticated: bool = False
    reachable: bool = False
    model_available: bool = False
    inference_ready: bool = False
    last_error_code: str = ""
    last_error_message: str = ""

    model_config = ConfigDict(extra="forbid")


class EmbeddingRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: "")
    correlation_id: str = Field(default_factory=lambda: "")
    texts: List[str] = Field(..., min_length=1)
    provider_preference: Optional[str] = None
    model_preference: Optional[str] = None
    local_only: bool = True
    cloud_allowed: bool = False
    cloud_authority_reference: str = ""
    max_cost: Optional[float] = None

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class EmbeddingResult(BaseModel):
    provider: str
    model: str
    embeddings: List[List[float]] = Field(default_factory=list)
    dimensions: int = 0
    semantic: bool = True
    correlation_id: str = ""

    model_config = ConfigDict(extra="forbid")
