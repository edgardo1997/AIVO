"""SQLite schema and immutable state contracts for the control boundary."""

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, Field

from sentinel.contracts import DecisionResultV1
from sentinel.contracts._base import require_timezone

SCHEMA_VERSION = 2


class PersistentControlState(str, Enum):
    NEW = "NEW"
    PENDING_VALIDATION = "PENDING_VALIDATION"
    RESERVED = "RESERVED"
    CANARY_SELECTED = "CANARY_SELECTED"
    COMMITTED = "COMMITTED"
    ROLLED_BACK = "ROLLED_BACK"
    EXPIRED = "EXPIRED"
    BLOCKED = "BLOCKED"


TERMINAL_STATES = frozenset(
    {
        PersistentControlState.COMMITTED,
        PersistentControlState.ROLLED_BACK,
        PersistentControlState.EXPIRED,
        PersistentControlState.BLOCKED,
    }
)

VALID_TRANSITIONS = {
    PersistentControlState.NEW: frozenset(
        {
            PersistentControlState.PENDING_VALIDATION,
            PersistentControlState.EXPIRED,
            PersistentControlState.BLOCKED,
        }
    ),
    PersistentControlState.PENDING_VALIDATION: frozenset(
        {
            PersistentControlState.RESERVED,
            PersistentControlState.EXPIRED,
            PersistentControlState.BLOCKED,
        }
    ),
    PersistentControlState.RESERVED: frozenset(
        {
            PersistentControlState.CANARY_SELECTED,
            PersistentControlState.EXPIRED,
            PersistentControlState.BLOCKED,
        }
    ),
    PersistentControlState.CANARY_SELECTED: frozenset(
        {
            PersistentControlState.COMMITTED,
            PersistentControlState.ROLLED_BACK,
            PersistentControlState.BLOCKED,
        }
    ),
}


class PersistentControlRecordV1(DecisionResultV1):
    correlation_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    issuer_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    signature: str = Field(pattern=r"^[A-Za-z0-9_=-]{80,128}$")
    state: PersistentControlState
    activation_state: str
    rollback_state: str
    audit_reference: str | None = None
    created_at: Annotated[datetime, AfterValidator(require_timezone)]
    updated_at: Annotated[datetime, AfterValidator(require_timezone)]


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS control_records (
    correlation_id TEXT PRIMARY KEY,
    evidence_hash TEXT NOT NULL,
    issuer_id TEXT NOT NULL,
    signature TEXT NOT NULL,
    state TEXT NOT NULL,
    activation_state TEXT NOT NULL,
    rollback_state TEXT NOT NULL,
    audit_reference TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS control_audit (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    previous_state TEXT,
    new_state TEXT NOT NULL,
    result TEXT NOT NULL
);
"""
