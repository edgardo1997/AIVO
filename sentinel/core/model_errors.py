"""Stable routing and provider error taxonomy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


class RoutingError(Exception):
    def __init__(
        self,
        code: str,
        safe_message: str,
        retryable: bool = False,
        recommended_action: str = "",
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.safe_message = safe_message
        self.retryable = retryable
        self.recommended_action = recommended_action
        self.details = details or {}
        super().__init__(safe_message)

    def to_safe_dict(self, correlation_id: str = "") -> Dict[str, Any]:
        return {
            "error_code": self.code,
            "safe_message": self.safe_message,
            "correlation_id": correlation_id,
            "retryable": self.retryable,
            "recommended_action": self.recommended_action,
            "details": self.details,
        }


@dataclass(frozen=True)
class RoutingErrorCode:
    PROVIDER_NOT_CONFIGURED = "SEN-PROVIDER-NOT-CONFIGURED"
    PROVIDER_DISABLED = "SEN-PROVIDER-DISABLED"
    PROVIDER_UNAVAILABLE = "SEN-PROVIDER-UNAVAILABLE"
    PROVIDER_AUTH_FAILED = "SEN-PROVIDER-AUTH-FAILED"
    PROVIDER_RATE_LIMITED = "SEN-PROVIDER-RATE-LIMITED"
    PROVIDER_CIRCUIT_OPEN = "SEN-PROVIDER-CIRCUIT-OPEN"
    MODEL_NOT_FOUND = "SEN-MODEL-NOT-FOUND"
    MODEL_NOT_READY = "SEN-MODEL-NOT-READY"
    MODEL_CAPABILITY_MISMATCH = "SEN-MODEL-CAPABILITY-MISMATCH"
    MODEL_CONTEXT_EXCEEDED = "SEN-MODEL-CONTEXT-EXCEEDED"
    MODEL_BUDGET_EXCEEDED = "SEN-MODEL-BUDGET-EXCEEDED"
    MODEL_CLOUD_NOT_AUTHORIZED = "SEN-MODEL-CLOUD-NOT-AUTHORIZED"
    MODEL_ROUTING_FAILED = "SEN-MODEL-ROUTING-FAILED"
    MODEL_STREAM_FAILED = "SEN-MODEL-STREAM-FAILED"
