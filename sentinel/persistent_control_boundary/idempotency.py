"""Persistent reservation API preventing replay and evidence substitution."""

from .schema import PersistentControlRecordV1, PersistentControlState
from .transaction import PersistentControlTransaction


class PersistentControlIdempotency:
    def __init__(self, transaction: PersistentControlTransaction) -> None:
        self.transaction = transaction

    def reserve(
        self,
        *,
        correlation_id: str,
        evidence_hash: str,
        issuer_id: str,
        signature: str,
    ) -> PersistentControlRecordV1:
        record = self.transaction.create(
            correlation_id=correlation_id,
            evidence_hash=evidence_hash,
            issuer_id=issuer_id,
            signature=signature,
        )
        if record.state is PersistentControlState.NEW:
            record = self.transaction.transition(
                correlation_id=correlation_id,
                evidence_hash=evidence_hash,
                issuer_id=issuer_id,
                signature=signature,
                target=PersistentControlState.PENDING_VALIDATION,
            )
        if record.state is PersistentControlState.PENDING_VALIDATION:
            record = self.transaction.transition(
                correlation_id=correlation_id,
                evidence_hash=evidence_hash,
                issuer_id=issuer_id,
                signature=signature,
                target=PersistentControlState.RESERVED,
            )
        return record
