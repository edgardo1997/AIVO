import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class CloudAuthorizationError(Exception):
    def __init__(self, message: str, reason: str = "denied"):
        super().__init__(message)
        self.reason = reason


@dataclass
class CloudExecutionAuthorization:
    cloud_allowed: bool = False
    allowed_providers: List[str] = field(default_factory=list)
    allowed_models: List[str] = field(default_factory=list)
    allowed_request_purposes: List[str] = field(default_factory=list)
    allowed_data_classifications: List[str] = field(default_factory=list)
    paid_use_allowed: bool = False
    automatic_fallback_allowed: bool = False
    maximum_cost_per_request: float = 0.0
    maximum_cost_per_period: float = 0.0
    issued_by: str = ""
    issued_at: float = 0.0
    expires_at: Optional[float] = None
    revoked_at: Optional[float] = None
    scope: str = ""
    reason: str = ""

    def is_expired(self, now: Optional[float] = None) -> bool:
        now = now or time.monotonic()
        if self.expires_at is not None and now > self.expires_at:
            return True
        if self.revoked_at is not None:
            return True
        return False

    def permits(
        self,
        provider: str,
        model: str,
        purpose: str = "conversation",
        data_classification: str = "ordinary_personal",
        estimated_cost: float = 0.0,
    ) -> bool:
        if not self.cloud_allowed:
            return False
        if self.is_expired():
            return False
        if self.allowed_providers and provider not in self.allowed_providers:
            return False
        if self.allowed_models and model not in self.allowed_models:
            return False
        if self.allowed_request_purposes and purpose not in self.allowed_request_purposes:
            return False
        if self.allowed_data_classifications and data_classification not in self.allowed_data_classifications:
            return False
        if estimated_cost > 0 and not self.paid_use_allowed:
            return False
        if self.maximum_cost_per_request > 0 and estimated_cost > self.maximum_cost_per_request:
            return False
        return True


class CloudAuthority:
    """Authoritative owner for cloud execution permission."""

    def __init__(self, default_local: bool = True):
        self._default_local = default_local
        self._standing: Dict[str, CloudExecutionAuthorization] = {}
        self._one_time: List[CloudExecutionAuthorization] = []
        self._local_only_mode = False
        self._offline_mode = False

    @property
    def local_only(self) -> bool:
        return self._local_only_mode

    def set_local_only(self, enabled: bool) -> None:
        self._local_only_mode = enabled

    def set_offline(self, enabled: bool) -> None:
        self._offline_mode = enabled

    def add_standing_policy(self, policy: CloudExecutionAuthorization, name: str = "default") -> None:
        self._standing[name] = policy

    def revoke_standing(self, name: str = "default") -> None:
        if name in self._standing:
            self._standing[name].revoked_at = time.monotonic()

    def issue_one_time_consent(
        self,
        provider: str,
        model: str,
        purpose: str = "conversation",
        data_classification: str = "ordinary_personal",
        paid: bool = False,
        max_cost: float = 0.0,
        scope: str = "single_request",
        reason: str = "",
    ) -> CloudExecutionAuthorization:
        auth = CloudExecutionAuthorization(
            cloud_allowed=True,
            allowed_providers=[provider],
            allowed_models=[model],
            allowed_request_purposes=[purpose],
            allowed_data_classifications=[data_classification],
            paid_use_allowed=paid,
            maximum_cost_per_request=max_cost,
            issued_by="user_consent",
            issued_at=time.monotonic(),
            expires_at=time.monotonic() + 60.0,
            scope=scope,
            reason=reason,
        )
        self._one_time.append(auth)
        return auth

    def consume_one_time_consent(self, consent: CloudExecutionAuthorization) -> None:
        if consent in self._one_time:
            self._one_time.remove(consent)
            consent.revoked_at = time.monotonic()

    def is_authorized(
        self,
        provider: str,
        model: str,
        purpose: str = "conversation",
        data_classification: str = "ordinary_personal",
        estimated_cost: float = 0.0,
    ) -> bool:
        if self._offline_mode:
            return False
        if self._local_only_mode:
            return False
        if not self._standing and not self._one_time:
            return False
        for auth in list(self._one_time) + list(self._standing.values()):
            if auth.permits(provider, model, purpose, data_classification, estimated_cost):
                return True
        return False

    def require_authorization_reason(
        self,
        provider: str,
        model: str,
        purpose: str = "conversation",
        data_classification: str = "ordinary_personal",
        estimated_cost: float = 0.0,
    ) -> Optional[str]:
        if self._offline_mode:
            return "Offline mode is active"
        if self._local_only_mode:
            return "Local-only mode is active"
        if not self._standing and not self._one_time:
            return "No cloud authorization configured"
        for auth in list(self._one_time) + list(self._standing.values()):
            if not auth.cloud_allowed:
                continue
            if auth.allowed_providers and provider not in auth.allowed_providers:
                return f"Provider {provider} not in authorized providers"
            if auth.allowed_models and model not in auth.allowed_models:
                return f"Model {model} not in authorized models"
            if auth.allowed_request_purposes and purpose not in auth.allowed_request_purposes:
                return "Purpose not in authorized purposes"
            if auth.allowed_data_classifications and data_classification not in auth.allowed_data_classifications:
                return "Data classification not in authorized classes"
            if estimated_cost > 0 and not auth.paid_use_allowed:
                return "Paid use not authorized"
            if auth.maximum_cost_per_request > 0 and estimated_cost > auth.maximum_cost_per_request:
                return "Estimated cost exceeds request cap"
            return None
        return "No matching cloud authorization"
