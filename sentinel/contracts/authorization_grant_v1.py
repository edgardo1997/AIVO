"""Tamper-evident, single-use authorization grant contracts.

AuthorizationGrantV1 remains disconnected from ToolGateway. Its transition
methods return new immutable values and perform no persistence or execution.
"""

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    model_validator,
)

from ._base import (
    FROZEN_MODEL_CONFIG,
    NonEmptyString,
    require_timezone,
)
from .identity_context_v1 import IdentityContextV1
from .simulation_result_v1 import SimulationActionTypeV1


AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]


class AuthorizedStepV1(BaseModel):
    """Exact step and parameter digest covered by an authorization."""

    model_config = FROZEN_MODEL_CONFIG

    step_id: NonEmptyString
    tool_id: NonEmptyString
    params_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class AuthorizationScopeV1(str, Enum):
    READ_ONLY = "READ_ONLY"
    SIMULATION_ONLY = "SIMULATION_ONLY"
    USER_APPROVED_ACTION = "USER_APPROVED_ACTION"


class AuthorizationStatusV1(str, Enum):
    AUTH_PENDING = "AUTH_PENDING"
    AUTHORIZED_LIMITED = "AUTHORIZED_LIMITED"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    AUTH_REVOKED = "AUTH_REVOKED"
    AUTH_DENIED = "AUTH_DENIED"


class AuthorizationGrantV1(BaseModel):
    """Immutable, hash-verified authorization scoped to plan steps."""

    model_config = FROZEN_MODEL_CONFIG

    schema_version: Literal["1.0"]
    authorization_id: NonEmptyString
    plan_id: NonEmptyString
    user_id: NonEmptyString
    policy_decision_id: NonEmptyString
    issuer: NonEmptyString
    nonce: NonEmptyString
    authorized_tools: tuple[NonEmptyString, ...] = Field(min_length=1)
    authorized_steps: tuple[AuthorizedStepV1, ...] = Field(min_length=1)
    params_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    grant_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    expires_at: AwareDatetime
    single_use: Literal[True]
    created_at: AwareDatetime
    consumed_at: AwareDatetime | None = None
    identity_context: IdentityContextV1 | None = None
    authority: Literal[False] = False
    execution_requested: Literal[False] = False

    # Optional compatibility extension for the passive consent boundary.
    grant_id: NonEmptyString | None = None
    correlation_id: NonEmptyString | None = None
    consent_id: NonEmptyString | None = None
    evidence_hash: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    issuer_id: NonEmptyString | None = None
    scope: AuthorizationScopeV1 | None = None
    allowed_action: SimulationActionTypeV1 | None = None
    revoked: bool | None = None
    status: AuthorizationStatusV1 | None = None

    @staticmethod
    def calculate_grant_hash(
        *,
        authorization_id: str,
        plan_id: str,
        user_id: str,
        policy_decision_id: str,
        issuer: str,
        nonce: str,
        authorized_tools: tuple[str, ...] | list[str],
        authorized_steps: (tuple[AuthorizedStepV1, ...] | list[AuthorizedStepV1]),
        params_hash: str,
        expires_at: datetime,
        single_use: bool,
        created_at: datetime,
        consumed_at: datetime | None,
        identity_context: IdentityContextV1 | None = None,
        grant_id: str | None = None,
        correlation_id: str | None = None,
        consent_id: str | None = None,
        evidence_hash: str | None = None,
        issuer_id: str | None = None,
        scope: AuthorizationScopeV1 | None = None,
        allowed_action: SimulationActionTypeV1 | None = None,
        revoked: bool | None = None,
        status: AuthorizationStatusV1 | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "authorization_id": authorization_id,
            "plan_id": plan_id,
            "user_id": user_id,
            "policy_decision_id": policy_decision_id,
            "issuer": issuer,
            "nonce": nonce,
            "authorized_tools": list(authorized_tools),
            "authorized_steps": [step.model_dump(mode="json") for step in authorized_steps],
            "params_hash": params_hash,
            "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
            "single_use": single_use,
            "created_at": created_at.astimezone(timezone.utc).isoformat(),
            "consumed_at": (consumed_at.astimezone(timezone.utc).isoformat() if consumed_at is not None else None),
            "identity_context": (identity_context.model_dump(mode="json") if identity_context is not None else None),
            "grant_id": grant_id,
            "correlation_id": correlation_id,
            "consent_id": consent_id,
            "evidence_hash": evidence_hash,
            "issuer_id": issuer_id,
            "scope": scope.value if scope is not None else None,
            "allowed_action": (allowed_action.value if allowed_action is not None else None),
            "revoked": revoked,
            "status": status.value if status is not None else None,
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def issue(
        cls,
        *,
        authorization_id: str,
        plan_id: str,
        user_id: str,
        policy_decision_id: str,
        issuer: str,
        nonce: str,
        authorized_steps: (tuple[AuthorizedStepV1, ...] | list[AuthorizedStepV1]),
        params_hash: str,
        expires_at: datetime,
        created_at: datetime,
        identity_context: IdentityContextV1 | None = None,
    ) -> "AuthorizationGrantV1":
        steps = tuple(authorized_steps)
        tools = tuple(dict.fromkeys(step.tool_id for step in steps))
        grant_hash = cls.calculate_grant_hash(
            authorization_id=authorization_id,
            plan_id=plan_id,
            user_id=user_id,
            policy_decision_id=policy_decision_id,
            issuer=issuer,
            nonce=nonce,
            authorized_tools=tools,
            authorized_steps=steps,
            params_hash=params_hash,
            expires_at=expires_at,
            single_use=True,
            created_at=created_at,
            consumed_at=None,
            identity_context=identity_context,
            grant_id=None,
            correlation_id=None,
            consent_id=None,
            evidence_hash=None,
            issuer_id=None,
            scope=None,
            allowed_action=None,
            revoked=None,
            status=None,
        )
        return cls(
            schema_version="1.0",
            authorization_id=authorization_id,
            plan_id=plan_id,
            user_id=user_id,
            policy_decision_id=policy_decision_id,
            issuer=issuer,
            nonce=nonce,
            authorized_tools=tools,
            authorized_steps=steps,
            params_hash=params_hash,
            grant_hash=grant_hash,
            expires_at=expires_at,
            single_use=True,
            created_at=created_at,
            consumed_at=None,
            identity_context=identity_context,
        )

    @classmethod
    def issue_limited(
        cls,
        *,
        grant_id: str,
        correlation_id: str,
        consent_id: str,
        evidence_hash: str,
        issuer_id: str,
        scope: AuthorizationScopeV1,
        allowed_action: SimulationActionTypeV1,
        status: AuthorizationStatusV1,
        policy_decision_id: str,
        decision_source: str,
        created_at: datetime,
        expires_at: datetime,
        nonce: str,
        revoked: bool = False,
        params_hash: str | None = None,
        plan_id: str | None = None,
        step_id: str | None = None,
        tool_id: str = "authorization.passive",
    ) -> "AuthorizationGrantV1":
        effective_params_hash = params_hash or evidence_hash
        authorized_step = AuthorizedStepV1(
            step_id=step_id or f"passive:{allowed_action.value.lower()}",
            tool_id=tool_id,
            params_hash=effective_params_hash,
        )
        tools = (authorized_step.tool_id,)
        grant_hash = cls.calculate_grant_hash(
            authorization_id=grant_id,
            plan_id=plan_id or f"consent:{consent_id}",
            user_id=decision_source,
            policy_decision_id=policy_decision_id,
            issuer=issuer_id,
            nonce=nonce,
            authorized_tools=tools,
            authorized_steps=(authorized_step,),
            params_hash=effective_params_hash,
            expires_at=expires_at,
            single_use=True,
            created_at=created_at,
            consumed_at=None,
            grant_id=grant_id,
            correlation_id=correlation_id,
            consent_id=consent_id,
            evidence_hash=evidence_hash,
            issuer_id=issuer_id,
            scope=scope,
            allowed_action=allowed_action,
            revoked=revoked,
            status=status,
        )
        return cls(
            schema_version="1.0",
            authorization_id=grant_id,
            plan_id=plan_id or f"consent:{consent_id}",
            user_id=decision_source,
            policy_decision_id=policy_decision_id,
            issuer=issuer_id,
            nonce=nonce,
            authorized_tools=tools,
            authorized_steps=(authorized_step,),
            params_hash=effective_params_hash,
            grant_hash=grant_hash,
            expires_at=expires_at,
            single_use=True,
            created_at=created_at,
            grant_id=grant_id,
            correlation_id=correlation_id,
            consent_id=consent_id,
            evidence_hash=evidence_hash,
            issuer_id=issuer_id,
            scope=scope,
            allowed_action=allowed_action,
            revoked=revoked,
            status=status,
        )

    @model_validator(mode="after")
    def validate_integrity(self) -> "AuthorizationGrantV1":
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be later than created_at")
        if self.consumed_at is not None:
            if self.consumed_at < self.created_at:
                raise ValueError("consumed_at must not be earlier than created_at")
            if self.consumed_at > self.expires_at:
                raise ValueError("consumed_at must not be later than expires_at")

        step_tools = tuple(dict.fromkeys(step.tool_id for step in self.authorized_steps))
        if self.authorized_tools != step_tools:
            raise ValueError("authorized_tools must match tools in authorized_steps")
        if self.identity_context is not None and self.identity_context.user_id != self.user_id:
            raise ValueError("identity_context.user_id must match grant user_id")

        limited_values = (
            self.grant_id,
            self.correlation_id,
            self.consent_id,
            self.evidence_hash,
            self.issuer_id,
            self.scope,
            self.allowed_action,
            self.revoked,
            self.status,
        )
        if any(value is not None for value in limited_values):
            if any(value is None for value in limited_values):
                raise ValueError("limited authorization fields must be supplied together")
            if self.grant_id != self.authorization_id:
                raise ValueError("grant_id must match authorization_id")
            if self.issuer_id != self.issuer:
                raise ValueError("issuer_id must match issuer")
            if (self.status is AuthorizationStatusV1.AUTH_REVOKED) != self.revoked:
                raise ValueError("revoked flag must match AUTH_REVOKED status")

        expected = self.calculate_grant_hash(
            authorization_id=self.authorization_id,
            plan_id=self.plan_id,
            user_id=self.user_id,
            policy_decision_id=self.policy_decision_id,
            issuer=self.issuer,
            nonce=self.nonce,
            authorized_tools=self.authorized_tools,
            authorized_steps=self.authorized_steps,
            params_hash=self.params_hash,
            expires_at=self.expires_at,
            single_use=self.single_use,
            created_at=self.created_at,
            consumed_at=self.consumed_at,
            identity_context=self.identity_context,
            grant_id=self.grant_id,
            correlation_id=self.correlation_id,
            consent_id=self.consent_id,
            evidence_hash=self.evidence_hash,
            issuer_id=self.issuer_id,
            scope=self.scope,
            allowed_action=self.allowed_action,
            revoked=self.revoked,
            status=self.status,
        )
        if self.grant_hash != expected:
            raise ValueError("grant_hash does not match canonical grant contents")
        return self

    def assert_usable(
        self,
        *,
        at: datetime | None = None,
    ) -> None:
        """Validate temporal and replay state without changing external state."""
        now = at or datetime.now(timezone.utc)
        require_timezone(now)
        if self.status is not None and self.status is not AuthorizationStatusV1.AUTHORIZED_LIMITED:
            raise PermissionError("limited authorization is not in AUTHORIZED_LIMITED state")
        if self.revoked:
            raise PermissionError("limited authorization has been revoked")
        if self.consumed_at is not None:
            raise PermissionError("authorization grant has already been consumed")
        if now < self.created_at:
            raise PermissionError("authorization grant is not active yet")
        if now >= self.expires_at:
            raise PermissionError("authorization grant has expired")

    def mark_consumed(self, consumed_at: datetime) -> "AuthorizationGrantV1":
        """Return a consumed immutable grant; reject replay attempts."""
        self.assert_usable(at=consumed_at)
        updated_hash = self.calculate_grant_hash(
            authorization_id=self.authorization_id,
            plan_id=self.plan_id,
            user_id=self.user_id,
            policy_decision_id=self.policy_decision_id,
            issuer=self.issuer,
            nonce=self.nonce,
            authorized_tools=self.authorized_tools,
            authorized_steps=self.authorized_steps,
            params_hash=self.params_hash,
            expires_at=self.expires_at,
            single_use=True,
            created_at=self.created_at,
            consumed_at=consumed_at,
            identity_context=self.identity_context,
            grant_id=self.grant_id,
            correlation_id=self.correlation_id,
            consent_id=self.consent_id,
            evidence_hash=self.evidence_hash,
            issuer_id=self.issuer_id,
            scope=self.scope,
            allowed_action=self.allowed_action,
            revoked=self.revoked,
            status=self.status,
        )
        return type(self).model_validate(
            {
                **self.model_dump(),
                "consumed_at": consumed_at,
                "grant_hash": updated_hash,
            }
        )
