"""Authenticated, payload-free operational evidence contract."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import AfterValidator, Field

from ._base import require_timezone
from .authority import NonAuthoritativeDecisionV1

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]
HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]
SignatureValue = Annotated[str, Field(pattern=r"^[A-Za-z0-9_=-]{80,128}$")]


class EvidenceIntegrityStatusV1(str, Enum):
    UNKNOWN = "UNKNOWN"
    SIGNED = "SIGNED"
    VERIFIED = "VERIFIED"
    INVALID = "INVALID"


class EvidenceSignalV1(NonAuthoritativeDecisionV1):
    """Signed evidence metadata; operational payloads are never retained."""

    evidence_id: SafeIdentifier
    issuer_id: SafeIdentifier
    schema_version: Literal["1.0"] = "1.0"
    created_at: AwareDatetime
    correlation_id: SafeIdentifier
    payload_hash: HashValue
    signature: SignatureValue
    integrity_status: EvidenceIntegrityStatusV1
