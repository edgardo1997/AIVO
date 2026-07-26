"""Bounded retention preserving critical incident evidence."""

from pydantic import BaseModel, ConfigDict, Field

from .storage import OperationalEvidenceStorage


class EvidenceRetentionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    maximum_records: int = Field(gt=0, le=1_000_000)

    def apply(self, storage: OperationalEvidenceStorage) -> int:
        excess = storage.count() - self.maximum_records
        if excess <= 0:
            return 0
        with storage.connection:
            cursor = storage.connection.execute(
                "DELETE FROM operational_evidence WHERE event_id_hash IN ("
                "SELECT event_id_hash FROM operational_evidence "
                "WHERE incident_state NOT IN "
                "('INCIDENT_CRITICAL', 'INCIDENT_ROLLBACK_REQUIRED') "
                "ORDER BY timestamp LIMIT ?)",
                (excess,),
            )
        return max(0, cursor.rowcount)
