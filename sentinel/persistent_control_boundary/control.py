"""Opt-in lifecycle for the persistent control boundary."""

import os
from pathlib import Path

from .idempotency import PersistentControlIdempotency
from .recovery import PersistentRecoveryInspector
from .rollback import PersistentRollbackCoordinator
from .storage import PersistentControlStorage
from .transaction import PersistentControlTransaction

PERSISTENT_CONTROL_BOUNDARY_ENABLED = False
_ENV_NAME = "PERSISTENT_CONTROL_BOUNDARY_ENABLED"


class PersistentControlBoundary:
    authority = False
    execution_requested = False

    def __init__(
        self,
        *,
        database_path: Path,
        enabled: bool | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        source = os.environ if environ is None else environ
        raw = source.get(_ENV_NAME)
        self.enabled = (
            PERSISTENT_CONTROL_BOUNDARY_ENABLED
            if enabled is None and raw is None
            else raw.strip().lower() in {"1", "true", "yes", "on"}
            if enabled is None
            else enabled
        )
        self.storage = PersistentControlStorage(database_path) if self.enabled else None
        self.transaction = PersistentControlTransaction(self.storage) if self.storage is not None else None
        self.idempotency = PersistentControlIdempotency(self.transaction) if self.transaction is not None else None
        self.rollback = PersistentRollbackCoordinator(self.transaction) if self.transaction is not None else None
        self.recovery = PersistentRecoveryInspector(self.storage) if self.storage is not None else None

    def close(self) -> None:
        if self.storage is not None:
            self.storage.close()
