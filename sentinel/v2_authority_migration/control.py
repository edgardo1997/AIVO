"""Feature control and state machine for limited migration."""

import os
from datetime import datetime, timezone
from enum import Enum

from .migration_policy import MigrationPolicyV1

V2_AUTHORITY_MIGRATION_ENABLED = False
V2_AUTHORITY_SCOPE: tuple[str, ...] = ()
_ENV_NAME = "V2_AUTHORITY_MIGRATION_ENABLED"


class AuthorityMigrationState(str, Enum):
    DISABLED = "DISABLED"
    SHADOW_ONLY = "SHADOW_ONLY"
    LIMITED_CANARY = "LIMITED_CANARY"
    ROLLBACK = "ROLLBACK"


class AuthorityMigrationController:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        scope: tuple[str, ...] | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        source = os.environ if environ is None else environ
        raw = source.get(_ENV_NAME)
        self.enabled = (
            V2_AUTHORITY_MIGRATION_ENABLED
            if enabled is None and raw is None
            else raw.strip().lower() in {"1", "true", "yes", "on"}
            if enabled is None
            else enabled
        )
        self.scope = tuple(V2_AUTHORITY_SCOPE if scope is None else scope)
        self.state = AuthorityMigrationState.SHADOW_ONLY if self.enabled else AuthorityMigrationState.DISABLED
        self.policy: MigrationPolicyV1 | None = None
        self.started_at: datetime | None = None

    def begin_limited_canary(
        self,
        *,
        policy: MigrationPolicyV1,
        readiness_approved: bool,
    ) -> bool:
        if (
            not self.enabled
            or not readiness_approved
            or not self.scope
            or not set(policy.allowed_operations).issubset(self.scope)
        ):
            return False
        self.policy = policy
        self.started_at = datetime.now(timezone.utc)
        self.state = AuthorityMigrationState.LIMITED_CANARY
        return True

    def rollback(self) -> None:
        if self.enabled:
            self.state = AuthorityMigrationState.ROLLBACK

    def trial_expired(self, now: datetime | None = None) -> bool:
        if self.started_at is None or self.policy is None:
            return True
        current = now or datetime.now(timezone.utc)
        return (current - self.started_at).total_seconds() > self.policy.maximum_trial_seconds
