"""Canonical, immutable identity context for future authorization binding."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Annotated, Literal

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


class IdentityContextV1(BaseModel):
    """Stable identity snapshot; disconnected from runtime authentication."""

    model_config = FROZEN_MODEL_CONFIG

    schema_version: Literal["1.0"]
    user_id: NonEmptyString
    session_id: NonEmptyString
    roles: tuple[NonEmptyString, ...] = Field(min_length=1)
    authentication_method: NonEmptyString
    created_at: Annotated[datetime, AfterValidator(require_timezone)]
    identity_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @staticmethod
    def canonical_values(
        *,
        user_id: str,
        session_id: str,
        roles: tuple[str, ...] | list[str],
        authentication_method: str,
        created_at: datetime,
    ) -> dict:
        return {
            "user_id": user_id.strip(),
            "session_id": session_id.strip(),
            "roles": sorted({role.strip().lower() for role in roles if role.strip()}),
            "authentication_method": authentication_method.strip().lower(),
            "created_at": created_at.astimezone(timezone.utc).isoformat(),
        }

    @classmethod
    def calculate_identity_hash(cls, **values) -> str:
        canonical = json.dumps(
            cls.canonical_values(**values),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        session_id: str,
        roles: tuple[str, ...] | list[str],
        authentication_method: str,
        created_at: datetime,
    ) -> "IdentityContextV1":
        canonical = cls.canonical_values(
            user_id=user_id,
            session_id=session_id,
            roles=roles,
            authentication_method=authentication_method,
            created_at=created_at,
        )
        return cls(
            schema_version="1.0",
            **canonical,
            identity_hash=cls.calculate_identity_hash(
                user_id=canonical["user_id"],
                session_id=canonical["session_id"],
                roles=canonical["roles"],
                authentication_method=canonical["authentication_method"],
                created_at=created_at,
            ),
        )

    @model_validator(mode="after")
    def validate_identity_hash(self) -> "IdentityContextV1":
        expected = self.calculate_identity_hash(
            user_id=self.user_id,
            session_id=self.session_id,
            roles=self.roles,
            authentication_method=self.authentication_method,
            created_at=self.created_at,
        )
        if self.identity_hash != expected:
            raise ValueError("identity_hash does not match canonical identity context")
        canonical_roles = tuple(
            self.canonical_values(
                user_id=self.user_id,
                session_id=self.session_id,
                roles=self.roles,
                authentication_method=self.authentication_method,
                created_at=self.created_at,
            )["roles"]
        )
        object.__setattr__(self, "roles", canonical_roles)
        object.__setattr__(
            self,
            "authentication_method",
            self.authentication_method.strip().lower(),
        )
        return self
