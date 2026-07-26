"""Opt-in controller that creates no storage while disabled."""

import os
from pathlib import Path
from typing import Literal

from .audit_store import AuthorityAuditStore
from .idempotency import PersistentIdempotencyManager
from .storage import AuthoritySafetyStorage

AUTHORITY_SAFETY_LAYER_ENABLED = False
_ENV_NAME = "AUTHORITY_SAFETY_LAYER_ENABLED"


class AuthoritySafetyControl:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        source = os.environ if environ is None else environ
        raw = source.get(_ENV_NAME)
        self.enabled = (
            AUTHORITY_SAFETY_LAYER_ENABLED
            if enabled is None and raw is None
            else raw.strip().lower() in {"1", "true", "yes", "on"}
            if enabled is None
            else enabled
        )


class AuthoritySafetyController:
    authority: Literal[False] = False

    def __init__(
        self,
        *,
        control: AuthoritySafetyControl,
        database_path: Path,
    ) -> None:
        self.control = control
        self.storage = AuthoritySafetyStorage(database_path) if control.enabled else None
        self.idempotency = PersistentIdempotencyManager(self.storage) if self.storage is not None else None
        self.audit = AuthorityAuditStore(self.storage) if self.storage is not None else None

    def close(self) -> None:
        if self.storage is not None:
            self.storage.close()
