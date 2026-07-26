"""Logical rollback coordinator; it never invokes a runtime."""

from .schema import PersistentControlRecordV1, PersistentControlState
from .transaction import PersistentControlTransaction


class PersistentRollbackCoordinator:
    def __init__(self, transaction: PersistentControlTransaction) -> None:
        self.transaction = transaction

    def rollback(
        self,
        *,
        correlation_id: str,
        evidence_hash: str,
        issuer_id: str,
        signature: str,
    ) -> PersistentControlRecordV1:
        return self.transaction.transition(
            correlation_id=correlation_id,
            evidence_hash=evidence_hash,
            issuer_id=issuer_id,
            signature=signature,
            target=PersistentControlState.ROLLED_BACK,
            activation_state="INACTIVE",
            rollback_state="ROLLBACK_RECORDED",
        )
